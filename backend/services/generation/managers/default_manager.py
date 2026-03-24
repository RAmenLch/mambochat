import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, List, Set

from backend.services.generation.worker.chat_worker import ChatWorker
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.services.stream_manager_service import stream_manager
from backend.services.mcp_connection_manager import McpConnectionError

# 导入新的核心层与装配层
from backend.services.generation.core.instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage,
    UpdateSubMessageStatus, UpdateSubMessageConfig, SetFinalStatus, InterruptGeneration
)
from backend.services.generation.builders.director import LLMInputDirector
from backend.services.generation.tools.base_tool_provider import BaseToolProvider

# 导入基类与 Handlers
from backend.services.generation.managers.base_manager import AbstractGenerateManager
from backend.services.generation.managers.stream_handlers.base_handler import StreamContext
from backend.services.generation.managers.stream_handlers.handlers import (
    HitlHandler, TextAndReasoningHandler, RoundClosureHandler,
    ToolExecutionHandler, ImageAndUsageHandler
)


class DefaultGenerateManager(AbstractGenerateManager):
    """
    V2 默认生成管理器。
    使用责任链模式 (Handlers) 处理流式事件，统筹标准对话生成流程。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)

        # 共享状态
        self._final_usage_data: Dict = {}
        self._created_stream_ids: Set[str] = set()
        self._pending_hitl_tool_calls = []

        # 注册流事件处理器 (责任链)
        self._handlers = [
            HitlHandler(),
            TextAndReasoningHandler(),
            RoundClosureHandler(),
            ToolExecutionHandler(),
            ImageAndUsageHandler()
        ]

    @staticmethod
    def _extract_run_uuid(lc_run_id: str) -> Optional[str]:
        if not lc_run_id: return None
        return lc_run_id[len("lc_run--"):] if lc_run_id.startswith("lc_run--") else lc_run_id

    async def _execute_generation(
            self, worker: ChatWorker, chat_id: str, assistant_message_id: str
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
            providers = director.get_providers()
            hitl_config = getattr(llm_input.agent_config, 'hitl_interrupt_on', {})
            tool_map = {t.name: t for t in llm_input.agent_config.tools if
                        hasattr(t, 'name')} if llm_input.agent_config.tools else {}

        except McpConnectionError as e:
            yield CreateSubMessage(
                sub_message_id=generate_uuid(), type=schemas_enums.SubMessageType.NORMAL.value,
                sortOrder=1, status=schemas_enums.MessageStatus.FAILED,
                initial_content=f"**生成已终止**：检测到配置的 MCP 服务不可用。\n\n错误信息：{e.error_message}"
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)
            return

        should_interrupt = False

        async for mode, event in worker.generate(llm_input):
            if await stream_manager.is_cancellation_requested(assistant_message_id):
                raise asyncio.CancelledError("Generation cancelled.")

            # 1. 构建共享上下文
            context = StreamContext(
                decode=self.decode, mode=mode, event=event,
                lc_run_uuid=self._extract_run_uuid(getattr(event, 'id', None)),
                providers=providers, tool_map=tool_map, hitl_config=hitl_config,
                created_stream_ids=self._created_stream_ids,
                pending_hitl_tool_calls=self._pending_hitl_tool_calls,
                final_usage_data=self._final_usage_data
            )

            # 2. 遍历责任链
            for handler in self._handlers:
                async for instruction in handler.handle(context):
                    if isinstance(instruction, InterruptGeneration):
                        context.should_interrupt = True
                        continue
                    yield instruction

            if context.should_interrupt:
                should_interrupt = True
                break

        # 3. 收尾
        async for instruction in self._finalize_generation(is_interrupted=should_interrupt):
            yield instruction

    async def _finalize_generation(self, is_interrupted: bool = False) -> AsyncGenerator[BaseInstruction, None]:
        """收尾阶段：闭合残余流，发送 Usage 统计"""
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

    async def _cleanup_on_exception(
            self, assistant_message_id: str, final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """异常清理逻辑"""
        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            elif "CancelledError" in str(type(exception)):
                error_content = "生成被用户取消。"
            else:
                error_content = f"发生未处理的异常: {str(exception)}"

        last_content_id = None
        for sub_id in list(self._created_stream_ids):
            if sub_id.endswith('-R'): yield UpdateSubMessageConfig(sub_message_id=sub_id, config={"is_minimal": True})
            if sub_id.endswith('-N'): last_content_id = sub_id
            yield UpdateSubMessageStatus(sub_message_id=sub_id, status=final_status)
        self._created_stream_ids.clear()

        if error_content:
            if last_content_id:
                yield AppendToSubMessage(sub_message_id=last_content_id, content=f"\n\n**错误:** {error_content}")
            else:
                yield CreateSubMessage(
                    sub_message_id=generate_uuid(), type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1, status=final_status, initial_content=error_content
                )
