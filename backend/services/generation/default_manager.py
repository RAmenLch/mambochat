# backend/services/generation/default_manager.py

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent
from backend.services.stream_manager_service import stream_manager
from backend.services.mcp_connection_manager import McpConnectionManager, McpConnectionError
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
    UpdateSubMessageConfig,
    SetFinalStatus,
    SaveAndPersistFile
)
from backend.services.generation.abstract_manager import AbstractGenerateManager
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.llm_input_builder import LLMInputBuilder


class DefaultGenerateManager(AbstractGenerateManager):
    """
    V2 默认生成管理器。

    职责：
    1. 负责标准的对话生成流程，支持文本、推理 (Reasoning)、工具调用 (MCP) 和多模态图片生成。
    2. 接管原 ReActAgentChatGenerateManager 的能力，通过 LangChain/LangGraph 的事件流驱动。
    3. 解析 OpenAiWorker 输出的 messages (流式) 和 updates (状态) 事件，转换为前端指令。
    4. 集成 MCP 连接管理，负责在生成前进行服务可用性熔断检查。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        # 状态追踪 ID
        self._reasoning_id: Optional[str] = None
        self._content_id: Optional[str] = None

        # 工具调用 ID 映射表: tool_call_id -> sub_message_id
        self._tool_sub_msg_map: Dict[str, str] = {}

        # 工具信息缓存: tool_call_id -> McpToolContent
        # 用于在接收到 Tool Result 时，结合之前的 Tool Call 信息构建完整的更新 Payload
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def _execute_generation(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        # 1. 初始化构建器
        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)

        # 预配置构建器 (切片、过滤、多模态支持)
        (
            builder
            .slice_until_message(assistant_message_id)
            .filter_sub_message_types(
                schemas_enums.SubMessageType.NORMAL.value,
                schemas_enums.SubMessageType.MCP_TOOL.value,
                schemas_enums.SubMessageType.FILE.value
            )
            .enable_image_with_model()
            .enable_cpl_filter()
            .enable_resource_prompt_merge()
        )

        try:
            # 2. 预加载素材以检查配置
            await builder._load_materials()

            # 3. 初始化 MCP 工具 (如果启用)
            # 这里会进行连接检查，如果服务不可用将抛出异常并熔断
            await self._setup_mcp_tools(builder)

            # 4. 构建 LLMInput
            llm_input = await builder.build()

        except McpConnectionError as e:
            # 熔断处理：如果 MCP 服务不可用，直接生成错误消息并终止，不消耗 LLM Token
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

        # 5. 执行生成循环
        # V2 Worker 返回的是 (mode, event) 元组流
        async for mode, event in worker.generate(llm_input):

            # 检查取消请求
            if await stream_manager.is_cancellation_requested(assistant_message_id):
                raise asyncio.CancelledError("Generation was cancelled by user request.")

            # 处理流式事件
            async for instruction in self._process_stream_event(mode, event):
                yield instruction

        # 6. 正常结束处理
        async for instruction in self._finalize_generation():
            yield instruction

    async def _setup_mcp_tools(self, builder: LLMInputBuilder):
        """配置并注入 MCP 工具，包含健康检查"""
        # 1. 检查 Chat 配置中启用的 MCP ID 列表或配置字典
        mcp_config_map = {}

        if builder.chat and builder.chat.modelParameters:
            try:
                params = json.loads(builder.chat.modelParameters) if isinstance(builder.chat.modelParameters,
                                                                                str) else builder.chat.modelParameters
                raw_config = params.get("enabled_mcp_ids")

                if isinstance(raw_config, list):
                    # 兼容旧格式：[id1, id2] -> {id1: {}, id2: {}}
                    mcp_config_map = {mcp_id: {} for mcp_id in raw_config}
                elif isinstance(raw_config, dict):
                    # 新格式：{id1: {key: val}, id2: {}}
                    mcp_config_map = raw_config

            except (json.JSONDecodeError, TypeError):
                pass

        if not mcp_config_map:
            return

        # 2. 使用连接管理器获取工具并检查状态
        # 如果有服务不可用，此处会抛出 McpConnectionError
        conn_manager = McpConnectionManager(self.db_session)
        tools = await conn_manager.get_tools_and_check_status(mcp_config_map)

        # 3. 注入工具到 Builder
        if tools:
            builder.set_tools(tools)

    async def _process_stream_event(self, mode: str, event: any) -> AsyncGenerator[BaseInstruction, None]:
        """
        核心解析逻辑：根据 mode 和 event 类型分发处理。
        依赖 Decode 工具类提取信息。
        """
        Decode = self.decode
        # --- 1. 处理文本内容 (Content) ---
        text_content = Decode.get_text_content(mode, event)
        if text_content:
            if not self._content_id:
                self._content_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._content_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
            yield AppendToSubMessage(sub_message_id=self._content_id, content=text_content)

        # --- 2. 处理推理内容 (Reasoning) ---
        reasoning_content = Decode.get_reasoning_content(mode, event)
        if reasoning_content:
            if not self._reasoning_id:
                self._reasoning_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._reasoning_id,
                    type=schemas_enums.SubMessageType.REASONING.value,
                    sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
            yield AppendToSubMessage(sub_message_id=self._reasoning_id, content=reasoning_content)

        # --- 3. 处理工具调用请求 (Tool Calls) ---
        # 通常在 mode='updates' 且 message 为 AIMessage 时出现
        from langchain_core.messages.tool import ToolCall
        tool_calls: list[ToolCall] = Decode.get_toolcall_content(mode, event)
        if tool_calls:
            for tool_call in tool_calls:
                # tool_call 结构: {'id': '...', 'name': '...', 'args': {...}, ...}
                tool_call_id = tool_call.get("id")

                # 构建 McpToolContent 对象
                # 注意：LangChain 的 args 通常已经是 dict，如果是 string 则需要解析
                args = tool_call.get("args")
                args_str = json.dumps(args, ensure_ascii=False) if args else "{}"

                tool_content = McpToolContent(
                    tool_call_id=tool_call_id,
                    name=tool_call.get("name"),
                    arguments=args_str
                )

                # 缓存工具信息，供后续 Result 阶段使用
                self._tool_info_cache[tool_call_id] = tool_content

                sub_id = generate_uuid()
                self._tool_sub_msg_map[tool_call_id] = sub_id

                # 创建 MCP_TOOL 类型的子消息
                yield CreateSubMessage(
                    sub_message_id=sub_id,
                    type=schemas_enums.SubMessageType.MCP_TOOL.value,
                    sortOrder=2,
                    status=schemas_enums.MessageStatus.GENERATING,
                    initial_content=tool_content.to_json_string(),
                    config={"is_minimal": True}
                )

        # --- 4. 处理工具执行结果 (Tool Results) ---
        # 通常在 mode='updates' 且 message 为 ToolMessage 时出现
        tool_result = Decode.get_toolcall_result(mode, event)
        if tool_result:
            # tool_result 结构: {'id': '...', 'text': '...'}
            tool_call_id = tool_result.get("id")
            result_text = tool_result.get("text")

            sub_id = self._tool_sub_msg_map.get(tool_call_id)

            # 从缓存中获取完整的工具信息
            if sub_id and tool_call_id in self._tool_info_cache:
                cached_content = self._tool_info_cache[tool_call_id]

                # 更新结果状态
                cached_content.result = result_text
                cached_content.is_error = False

                # 发送全量更新指令
                yield UpdateSubMessageContent(
                    sub_message_id=sub_id,
                    content=cached_content.to_json_string()
                )
                yield UpdateSubMessageStatus(
                    sub_message_id=sub_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )

        # --- 5. 处理生成的图片 (Images) ---
        image_data = Decode.get_image_url(mode, event)
        if image_data:
            # image_data 结构: {"image_url": {"url": "data:image/..."}}
            url = image_data.get("image_url", {}).get("url")
            if url and url.startswith("data:image"):
                async for instruction in self._handle_generated_image(url):
                    yield instruction

    async def _handle_generated_image(self, base64_url: str) -> AsyncGenerator[BaseInstruction, None]:
        """处理 Base64 图片数据：保存文件并创建子消息"""
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

            # 1. 保存文件指令
            yield SaveAndPersistFile(
                file_id=file_id,
                filename=filename,
                base64_data=encoded_data,
                mime_type=mime_type,
                management_type=schemas_enums.FileManagementType.SUB_MESSAGE.value
            )

            # 2. 创建文件子消息指令
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
            if self._content_id:
                yield AppendToSubMessage(
                    sub_message_id=self._content_id,
                    content=f"\n\n**处理生成图片时出错: {e}**"
                )

    async def _finalize_generation(self) -> AsyncGenerator[BaseInstruction, None]:
        """生成结束后的收尾工作"""
        # 1. 完成 Content
        if self._content_id:
            yield UpdateSubMessageStatus(
                sub_message_id=self._content_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )
            self._content_id = None

        # 2. 完成 Reasoning (并最小化)
        if self._reasoning_id:
            yield UpdateSubMessageConfig(
                sub_message_id=self._reasoning_id,
                config={"is_minimal": True}
            )
            yield UpdateSubMessageStatus(
                sub_message_id=self._reasoning_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )
            self._reasoning_id = None

        # 3. 设置最终状态
        yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """异常发生时的清理逻辑"""

        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            elif not isinstance(exception, (type(None),)):
                if "CancelledError" in str(type(exception)):
                    error_content = "生成被用户取消。"
                else:
                    error_content = f"发生未处理的异常: {str(exception)}"

        # 1. 更新 Reasoning 状态
        if self._reasoning_id:
            yield UpdateSubMessageConfig(
                sub_message_id=self._reasoning_id,
                config={"is_minimal": True}
            )
            yield UpdateSubMessageStatus(sub_message_id=self._reasoning_id, status=final_status)

        # 2. 更新 Content 状态
        if self._content_id:
            yield UpdateSubMessageStatus(sub_message_id=self._content_id, status=final_status)

        # 3. 生成错误消息
        if error_content:
            if self._content_id:
                yield AppendToSubMessage(
                    sub_message_id=self._content_id,
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
