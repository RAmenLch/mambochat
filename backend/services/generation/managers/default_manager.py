# backend/services/generation/managers/default_manager.py

import asyncio
import json
import traceback
from typing import AsyncGenerator, Optional, Dict, List, Set

from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.services.stream_manager_service import stream_manager, cancellable_aiter
from backend.services.mcp_connection_manager import McpConnectionError

from backend.services.generation.core.instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage,
    SetFinalStatus, InterruptGeneration, FailSubMessagesByMessage, UpdateSubMessageConfig, UpdateSubMessageStatus
)
from backend.services.generation.builders.director import LLMInputDirector
from backend.services.generation.tools.base_tool_provider import BaseToolProvider

from backend.services.generation.managers.base_manager import AbstractGenerateManager
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.managers.stream_handlers.base_handler import StreamContext, BaseStreamHandler
from backend.services.generation.managers.stream_handlers.handlers import (
    HitlHandler, TextAndReasoningHandler, RoundClosureHandler,
    ToolExecutionHandler, ImageAndUsageHandler, FinishReasonMonitorHandler
)
from backend.services.generation.managers.stream_handlers.finish_reason_classifier import FinishReasonClassifier


class DefaultGenerateManager(AbstractGenerateManager):
    """
    V2 默认生成管理器。
    使用责任链模式 (Handlers) 处理流式事件，统筹标准对话生成流程。
    """

    def __init__(self, db_session: AsyncSession, recover_from_error: bool = False):
        super().__init__(db_session)

        self._final_usage_data: Dict = {}
        self._created_stream_ids: Set[str] = set()
        self._pending_hitl_tool_calls = []
        self._recover_from_error = recover_from_error
        self._last_finish_reason: Optional[str] = None

        self._handlers: List[BaseStreamHandler] = [
            HitlHandler(),
            TextAndReasoningHandler(),
            RoundClosureHandler(),
            ToolExecutionHandler(),
            ImageAndUsageHandler(),
            FinishReasonMonitorHandler()
        ]

    @staticmethod
    def _extract_run_uuid(lc_run_id: Optional[str]) -> Optional[str]:
        if not lc_run_id: return None
        return lc_run_id[len("lc_run--"):] if lc_run_id.startswith("lc_run--") else lc_run_id

    async def _execute_generation(
            self, worker: AbstractGenerateWorker, chat_id: str, assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        director = LLMInputDirector(self.db_session, chat_id=chat_id)
        (
            director.slice_until_message(assistant_message_id)
            .filter_sub_message_types(
                schemas_enums.SubMessageType.NORMAL.value,
                schemas_enums.SubMessageType.MCP_TOOL.value,
                schemas_enums.SubMessageType.FILE.value,
                schemas_enums.SubMessageType.SUGGEST.value,
                schemas_enums.SubMessageType.REVIEW_TOOL.value
            )
            .enable_tools()
            .enable_image_with_model()
            .enable_cpl_filter()
            .enable_resource_prompt_merge()
            .enable_max_context_messages().set_manager_name(DefaultGenerateManager.__name__)
        )

        try:
            llm_input = await director.build()
            if self._recover_from_error:
                llm_input.agent_config.recover_from_error = True
            providers = director.get_providers()
            hitl_config = llm_input.agent_config.hitl_interrupt_on
            tools = llm_input.agent_config.tools or []
            tool_map: Dict[str, BaseTool] = {t.name: t for t in tools}

        except McpConnectionError as e:
            yield CreateSubMessage(
                sub_message_id=generate_uuid(), type=schemas_enums.SubMessageType.NORMAL.value,
                sortOrder=1, status=schemas_enums.MessageStatus.FAILED,
                initial_content=f"**生成已终止**：检测到配置的 MCP 服务不可用。\n\n错误信息：{e.error_message}"
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)
            return

        should_interrupt = False
        cancel_event = await stream_manager.get_cancel_event(assistant_message_id)

        try:
            async for mode, event in cancellable_aiter(worker.generate(llm_input), cancel_event):
                decoder = worker.resolve_decoder(event)

                event_id: Optional[str] = None
                if not isinstance(event, dict):
                    event_id = event.id
                context = StreamContext(
                    decode=decoder, mode=mode, event=event,
                    lc_run_uuid=self._extract_run_uuid(event_id),
                    providers=providers, tool_map=tool_map, hitl_config=hitl_config,
                    created_stream_ids=self._created_stream_ids,
                    pending_hitl_tool_calls=self._pending_hitl_tool_calls,
                    final_usage_data=self._final_usage_data
                )

                for handler in self._handlers:
                    async for instruction in handler.handle(context):
                        if isinstance(instruction, InterruptGeneration):
                            context.should_interrupt = True
                            continue
                        yield instruction

                # 从 Handler 链中提取最后一轮 finish_reason (last-wins)
                if context.last_finish_reason:
                    self._last_finish_reason = context.last_finish_reason

                if context.should_interrupt:
                    should_interrupt = True
                    break
        except asyncio.CancelledError:
            raise

        async for instruction in self._finalize_generation(is_interrupted=should_interrupt):
            yield instruction

    async def _finalize_generation(self, is_interrupted: bool = False) -> AsyncGenerator[BaseInstruction, None]:
        for sub_id in list(self._created_stream_ids):
            if sub_id.endswith('-R'):
                yield UpdateSubMessageConfig(sub_message_id=sub_id, config={"is_minimal": True})
            yield UpdateSubMessageStatus(sub_message_id=sub_id, status=schemas_enums.MessageStatus.COMPLETED)
        self._created_stream_ids.clear()

        if self._final_usage_data:
            yield CreateSubMessage(
                sub_message_id=generate_uuid(), type=schemas_enums.SubMessageType.USAGE.value,
                sortOrder=99, status=schemas_enums.MessageStatus.COMPLETED,
                initial_content=json.dumps(self._final_usage_data), config={"context_participation_length": 0}
            )

        if not is_interrupted:
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        # 异常 finish_reason -> 生成 ERROR 子消息提示用户
        if self._last_finish_reason:
            user_msg = FinishReasonClassifier.get_user_message(self._last_finish_reason)
            if user_msg:
                from backend.schemas.message import ErrorContent
                error_content = ErrorContent(message=user_msg, stack_trace="")
                yield CreateSubMessage(
                    sub_message_id=generate_uuid(),
                    type=schemas_enums.SubMessageType.ERROR.value,
                    sortOrder=97,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    initial_content=error_content.to_json_string(),
                    config={"context_participation_length": 0}
                )
            self._last_finish_reason = None

    async def _cleanup_on_exception(
            self, assistant_message_id: str, final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        error_message = ""
        error_stack = ""

        if exception:
            if isinstance(exception, RuntimeError):
                error_message = str(type(exception))+ ":" + str(exception)
            elif isinstance(exception, asyncio.CancelledError):
                error_message = "生成被用户取消。"
            else:
                error_message = f"发生未处理的异常: {str(exception)}"
            error_stack = traceback.format_exc()

        # 统一将所有 GENERATING 状态的子消息批量标记为 FAILED（含 reasoning 折叠处理）
        yield FailSubMessagesByMessage(message_id=assistant_message_id)

        # 创建 Error 类型的子消息，包含简短错误信息和完整堆栈（参与上下文）
        if error_message:
            from backend.schemas.message import ErrorContent
            error_content = ErrorContent(message=error_message, stack_trace=error_stack)
            yield CreateSubMessage(
                sub_message_id=generate_uuid(),
                type=schemas_enums.SubMessageType.ERROR.value,
                sortOrder=98,
                status=final_status,
                initial_content=error_content.to_json_string()
            )
