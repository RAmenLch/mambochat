# backend/services/generation/default_manager.py

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, List, Set

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import ReviewToolContent
from backend.services.stream_manager_service import stream_manager
from backend.services.mcp_connection_manager import McpConnectionError
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    UpdateSubMessageConfig,
    SetFinalStatus,
    SaveAndPersistFile,
    InterruptGeneration
)
from backend.services.generation.abstract_manager import AbstractGenerateManager
from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend.services.generation.tools.base_tool_provider import BaseToolProvider

from services.generation.worker.chat_worker import ChatWorker


class DefaultGenerateManager(AbstractGenerateManager):
    """
    V2 默认生成管理器。

    职责：
    1. 负责标准的对话生成流程，支持文本、推理 (Reasoning)、工具调用 (MCP/Suggest) 和多模态图片生成。
    2. 接管原 ReActAgentChatGenerateManager 的能力，通过 LangChain/LangGraph 的事件流驱动。
    3. 解析 Worker 输出的 messages (流式) 和 updates (状态) 事件，转换为前端指令。
    4. 通过 ToolProvider 架构管理 MCP 和 Suggest 等工具的生命周期。
    5. 处理人机交互审核 (HITL) 中断与恢复流程。

    子消息 ID 规则：
    - 每轮 LLM 调用由 lc_run_id 唯一标识。
    - Reasoning 子消息 ID = "{lc_run_uuid}-R"
    - Normal(正文) 子消息 ID = "{lc_run_uuid}-N"
    - 在 updates 事件到达时立即闭合对应轮次的子消息。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self._final_usage_data: Optional[Dict] = None

        # 追踪已创建但尚未闭合的流式子消息 ID
        self._created_stream_ids: Set[str] = set()

        self.providers: List[BaseToolProvider] = []
        self._hitl_tools_config: Dict[str, bool] = {}
        self._pending_hitl_tool_calls = []
        # 工具名称映射表，用于快速检索工具定义（含 Schema）
        self._tool_map: Dict[str, BaseTool] = {}

    @staticmethod
    def _extract_run_uuid(lc_run_id: str) -> Optional[str]:
        """
        从 LangChain 的 lc_run id 中提取纯 UUID 部分。
        例如: 'lc_run--019cf715-726a-73e3-a399-7da13a7e0e3e' -> '019cf715-726a-73e3-a399-7da13a7e0e3e'
        """
        if not lc_run_id:
            return None
        if lc_run_id.startswith("lc_run--"):
            return lc_run_id[len("lc_run--"):]
        # 兼容：如果已经是纯 UUID 或其他格式，直接返回
        return lc_run_id

    async def _execute_generation(
            self,
            worker: ChatWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)

        (
            builder
            .slice_until_message(assistant_message_id)
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
            .enable_max_context_messages()
        )

        try:
            llm_input = await builder.build()
            self.providers = builder.get_providers()
            self._hitl_tools_config = getattr(llm_input, 'hitl_interrupt_on', {})

            if llm_input.tools:
                self._tool_map = {t.name: t for t in llm_input.tools if hasattr(t, 'name')}

        except McpConnectionError as e:
            error_id = generate_uuid()
            yield CreateSubMessage(
                sub_message_id=error_id,
                type=schemas_enums.SubMessageType.NORMAL.value,
                sortOrder=1,
                status=schemas_enums.MessageStatus.FAILED,
                initial_content=f"**生成已终止**：检测到配置的 MCP 服务不可用。\n\n错误信息：{e.error_message}"
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)
            return

        should_interrupt = False

        async for mode, event in worker.generate(llm_input):

            if await stream_manager.is_cancellation_requested(assistant_message_id):
                raise asyncio.CancelledError("Generation was cancelled by user request.")

            async for instruction in self._process_stream_event(mode, event):
                if isinstance(instruction, InterruptGeneration):
                    should_interrupt = True
                    continue
                yield instruction

            if should_interrupt:
                break

        async for instruction in self._finalize_generation(is_interrupted=should_interrupt):
            yield instruction

    async def _process_stream_event(self, mode: str, event: any) -> AsyncGenerator[BaseInstruction, None]:
        Decode = self.decode

        # --- 1. HITL 中断处理 ---
        interrupt_data = Decode.get_hitl_interrupt(mode, event)
        if interrupt_data and "action_requests" in interrupt_data:
            current_batch_id = generate_uuid()

            reviewable_tool_calls = [
                tc for tc in self._pending_hitl_tool_calls
                if self._hitl_tools_config.get(tc.get("name"))
            ]

            for idx, action_req in enumerate(interrupt_data["action_requests"]):
                if idx < len(reviewable_tool_calls):
                    tool_call_id = reviewable_tool_calls[idx].get("id")
                else:
                    tool_call_id = action_req.get("id") or generate_uuid()

                name = action_req.get("name")
                args = action_req.get("args", {})

                target_tool = self._tool_map.get(name)
                input_schema = target_tool.args if target_tool else None

                review_content = ReviewToolContent(
                    tool_call_id=tool_call_id,
                    name=name,
                    arguments=args,
                    input_schema=input_schema,
                    description=action_req.get("description"),
                    interrupt_index=idx,
                    batch_id=current_batch_id,
                    decision=None
                )

                sub_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=sub_id,
                    type=schemas_enums.SubMessageType.REVIEW_TOOL.value,
                    sortOrder=2,
                    status=schemas_enums.MessageStatus.PENDING_REVIEW,
                    initial_content=review_content.to_json_string(),
                    config={"context_participation_length": 0}
                )
            yield InterruptGeneration()
            return

        # --- 2. HITL 中间件恢复数据 ---
        middleware_data = Decode.get_hitl_middleware_data(mode, event)
        if middleware_data:
            approved_calls = middleware_data.get("approved_calls", [])
            rejected_results = middleware_data.get("rejected_results", [])

            for call in approved_calls:
                tool_call_id = call.get("id")
                name = call.get("name")
                args = call.get("args") or {}
                target_tool = self._tool_map.get(name)

                for provider in self.providers:
                    if provider.matches_tool_name(name):
                        async for instruction in provider.create_call_instruction(
                                tool_call_id, name, args, tool_def=target_tool
                        ):
                            yield instruction
                        break

            for res in rejected_results:
                tool_call_id = res.get("id")
                name = res.get("name")
                content = res.get("content")
                target_tool = self._tool_map.get(name)

                for provider in self.providers:
                    if provider.matches_tool_name(name):
                        async for instruction in provider.create_call_instruction(
                                tool_call_id, name, {}, tool_def=target_tool
                        ):
                            yield instruction
                        async for instruction in provider.create_result_instruction(tool_call_id, content, True):
                            yield instruction
                        break

        # --- 3. 提取当前事件的 lc_run_uuid ---
        lc_run_uuid = None
        if hasattr(event, 'id') and event.id:
            lc_run_uuid = self._extract_run_uuid(event.id)

        # --- 4. 流式正文内容 ---
        text_content = Decode.get_text_content(mode, event)
        if text_content and lc_run_uuid:
            content_id = f"{lc_run_uuid}-N"
            if content_id not in self._created_stream_ids:
                self._created_stream_ids.add(content_id)
                yield CreateSubMessage(
                    sub_message_id=content_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
            yield AppendToSubMessage(sub_message_id=content_id, content=text_content)

        # --- 5. 流式推理内容 ---
        reasoning_content = Decode.get_reasoning_content(mode, event)
        if reasoning_content and lc_run_uuid:
            reasoning_id = f"{lc_run_uuid}-R"
            if reasoning_id not in self._created_stream_ids:
                self._created_stream_ids.add(reasoning_id)
                yield CreateSubMessage(
                    sub_message_id=reasoning_id,
                    type=schemas_enums.SubMessageType.REASONING.value,
                    sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
            yield AppendToSubMessage(sub_message_id=reasoning_id, content=reasoning_content)

        # --- 6. 轮次闭合：当 updates 模式的 AIMessage 到达时 ---
        if mode == "updates" and isinstance(event, AIMessage) and lc_run_uuid:
            reasoning_id = f"{lc_run_uuid}-R"
            content_id = f"{lc_run_uuid}-N"

            if reasoning_id in self._created_stream_ids:
                yield UpdateSubMessageConfig(
                    sub_message_id=reasoning_id,
                    config={"is_minimal": True}
                )
                yield UpdateSubMessageStatus(
                    sub_message_id=reasoning_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )
                self._created_stream_ids.discard(reasoning_id)

            if content_id in self._created_stream_ids:
                yield UpdateSubMessageStatus(
                    sub_message_id=content_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )
                self._created_stream_ids.discard(content_id)

        # --- 7. 工具调用 (来自 updates AIMessage) ---
        tool_calls = Decode.get_toolcall_content(mode, event)
        if tool_calls:
            has_hitl_tool = any(self._hitl_tools_config.get(tc.get("name")) for tc in tool_calls)

            if has_hitl_tool:
                self._pending_hitl_tool_calls = tool_calls

            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id")
                name = tool_call.get("name")
                args = tool_call.get("args") or {}

                if has_hitl_tool:
                    continue

                target_tool = self._tool_map.get(name)

                for provider in self.providers:
                    if provider.matches_tool_name(name):
                        async for instruction in provider.create_call_instruction(
                                tool_call_id, name, args, tool_def=target_tool
                        ):
                            yield instruction
                        break

        # --- 8. 工具执行结果 ---
        tool_result = Decode.get_toolcall_result(mode, event)
        if tool_result:
            tool_call_id = tool_result.get("id")
            result_text = tool_result.get("text")
            is_error = tool_result.get("is_error", False)

            for provider in self.providers:
                async for instruction in provider.create_result_instruction(tool_call_id, result_text, is_error):
                    yield instruction

        # --- 9. 生成图片 ---
        image_data = Decode.get_image_url(mode, event)
        if image_data:
            url = image_data.get("image_url", {}).get("url")
            if url and url.startswith("data:image"):
                async for instruction in self._handle_generated_image(url):
                    yield instruction

        # --- 10. 用量统计 ---
        usage_data = Decode.get_usage(mode, event)
        if usage_data:
            self._final_usage_data = usage_data

    async def _handle_generated_image(self, base64_url: str) -> AsyncGenerator[BaseInstruction, None]:
        try:
            if ',' in base64_url:
                header, encoded_data = base64_url.split(',', 1)
                mime_type = header.split(';')[0].split(':')[1]
            else:
                encoded_data = base64_url
                mime_type = "image/png"

            file_extension = mime_type.split('/')[-1] if '/' in mime_type else 'bin'
            filename = f"generated_image.{file_extension}"

            file_id = generate_uuid()
            sub_message_id = generate_uuid()

            yield SaveAndPersistFile(
                file_id=file_id,
                filename=filename,
                base64_data=encoded_data,
                mime_type=mime_type,
                management_type=schemas_enums.FileManagementType.SUB_MESSAGE.value
            )

            yield CreateSubMessage(
                sub_message_id=sub_message_id,
                type=schemas_enums.SubMessageType.FILE.value,
                sortOrder=2,
                status=schemas_enums.MessageStatus.COMPLETED,
                initial_content=file_id,
                config={}
            )
        except Exception as e:
            print(f"Error processing generated image: {e}")
            # 尝试找到最近的正文子消息追加错误信息
            content_ids = [sid for sid in self._created_stream_ids if sid.endswith('-N')]
            if content_ids:
                yield AppendToSubMessage(
                    sub_message_id=content_ids[-1],
                    content=f"\n\n**处理生成图片时出错: {e}**"
                )

    async def _finalize_generation(self, is_interrupted: bool = False) -> AsyncGenerator[BaseInstruction, None]:
        """
        收尾阶段。
        正常情况下，所有流式子消息已在 updates 事件中闭合。
        此处处理可能的残余（如异常中断的流）、Usage 统计和最终状态。
        """
        # 安全网：闭合任何未被 updates 事件正常关闭的子消息
        for sub_id in list(self._created_stream_ids):
            if sub_id.endswith('-R'):
                yield UpdateSubMessageConfig(
                    sub_message_id=sub_id,
                    config={"is_minimal": True}
                )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )
        self._created_stream_ids.clear()

        if self._final_usage_data:
            usage_id = generate_uuid()
            usage_content = json.dumps(self._final_usage_data)
            yield CreateSubMessage(
                sub_message_id=usage_id,
                type=schemas_enums.SubMessageType.USAGE.value,
                sortOrder=99,
                status=schemas_enums.MessageStatus.COMPLETED,
                initial_content=usage_content,
                config={"context_participation_length": 0}
            )

        # 核心：如果是因为审核中断而收尾，绝不能发出 COMPLETED 终态指令
        if not is_interrupted:
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:

        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            elif not isinstance(exception, (type(None),)):
                if "CancelledError" in str(type(exception)):
                    error_content = "生成被用户取消。"
                else:
                    error_content = f"发生未处理的异常: {str(exception)}"

        # 闭合所有仍然活跃的流式子消息
        last_content_id = None
        for sub_id in list(self._created_stream_ids):
            if sub_id.endswith('-R'):
                yield UpdateSubMessageConfig(
                    sub_message_id=sub_id,
                    config={"is_minimal": True}
                )
            if sub_id.endswith('-N'):
                last_content_id = sub_id
            yield UpdateSubMessageStatus(sub_message_id=sub_id, status=final_status)
        self._created_stream_ids.clear()

        if error_content:
            if last_content_id:
                yield AppendToSubMessage(
                    sub_message_id=last_content_id,
                    content=f"\n\n**错误:** {error_content}"
                )
            else:
                error_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=error_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=final_status,
                    initial_content=error_content
                )
