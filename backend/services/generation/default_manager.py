# backend/services/generation/default_manager.py

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
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
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.llm_input_builder import LLMInputBuilder

# Tool Providers
from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mcp_tool_provider import MCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider


class DefaultGenerateManager(AbstractGenerateManager):
    """
    V2 默认生成管理器。

    职责：
    1. 负责标准的对话生成流程，支持文本、推理 (Reasoning)、工具调用 (MCP/Suggest) 和多模态图片生成。
    2. 接管原 ReActAgentChatGenerateManager 的能力，通过 LangChain/LangGraph 的事件流驱动。
    3. 解析 OpenAiWorker 输出的 messages (流式) 和 updates (状态) 事件，转换为前端指令。
    4. 通过 ToolProvider 架构管理 MCP 和 Suggest 等工具的生命周期。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        # 状态追踪 ID
        self._reasoning_id: Optional[str] = None
        self._content_id: Optional[str] = None
        self._final_usage_data: Optional[Dict] = None

        # 工具提供者列表
        self.providers: List[BaseToolProvider] = []

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
                schemas_enums.SubMessageType.FILE.value,
                schemas_enums.SubMessageType.SUGGEST.value
            )
            .enable_image_with_model()
            .enable_cpl_filter()
            .enable_resource_prompt_merge()
            .enable_max_context_messages()
        )

        try:
            # 2. 预加载素材以检查配置
            await builder._load_materials()

            # 3. 初始化并配置工具提供者
            await self._setup_providers(builder)

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
            should_interrupt = False
            async for instruction in self._process_stream_event(mode, event):
                if isinstance(instruction, InterruptGeneration):
                    should_interrupt = True
                    continue
                yield instruction

            if should_interrupt:
                break

        # 6. 正常结束处理
        async for instruction in self._finalize_generation():
            yield instruction

    async def _setup_providers(self, builder: LLMInputBuilder):
        """配置并注入工具提供者 (MCP, Suggest)，处理 System Prompt 注入"""
        self.providers = []

        # 解析模型参数
        params = {}
        if builder.chat and builder.chat.modelParameters:
            try:
                if isinstance(builder.chat.modelParameters, str):
                    params = json.loads(builder.chat.modelParameters)
                else:
                    params = builder.chat.modelParameters
            except (json.JSONDecodeError, TypeError):
                pass

        # 1. 配置 MCP Provider
        mcp_config_map = {}
        raw_mcp_config = params.get("enabled_mcp_ids")
        if isinstance(raw_mcp_config, list):
            mcp_config_map = {mcp_id: {} for mcp_id in raw_mcp_config}
        elif isinstance(raw_mcp_config, dict):
            mcp_config_map = raw_mcp_config

        if mcp_config_map:
            self.providers.append(MCPToolProvider(self.db_session, mcp_config_map))

        # 2. 配置 Suggest Provider
        enable_suggest = params.get("enable_suggest", False)
        if enable_suggest:
            self.providers.append(SuggestToolProvider(enable_suggest=True))

        # 3. 获取所有工具并注入 Builder
        all_tools = []
        prompt_injections = []

        for provider in self.providers:
            # 获取工具 (此处可能抛出 McpConnectionError)
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            # 获取 Prompt 注入
            injection = provider.get_system_prompt_injection()
            if injection:
                prompt_injections.append(injection)

        if all_tools:
            builder.set_tools(all_tools)

        # 4. 处理 System Prompt 注入
        if prompt_injections:
            # 获取当前的 System Prompt (可能是 Chat 配置的，也可能是之前 override 的)
            current_prompt = builder._system_prompt_override or builder.chat.systemPrompt or ""
            new_prompt = current_prompt + "\n\n" + "\n".join(prompt_injections)
            builder.set_system_prompt(new_prompt)

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
                name = tool_call.get("name")
                args = tool_call.get("args") or {}

                # 查找匹配的 Provider 并生成指令
                for provider in self.providers:
                    if provider.matches_tool_name(name):
                        async for instruction in provider.create_call_instruction(tool_call_id, name, args):
                            yield instruction
                        break

        # --- 4. 处理工具执行结果 (Tool Results) ---
        # 通常在 mode='updates' 且 message 为 ToolMessage 时出现
        tool_result = Decode.get_toolcall_result(mode, event)
        if tool_result:
            # tool_result 结构: {'id': '...', 'text': '...'}
            tool_call_id = tool_result.get("id")
            result_text = tool_result.get("text")
            is_error = tool_result.get("is_error", False)

            # 遍历所有 Provider 尝试处理结果
            # Provider 内部会根据 tool_call_id 缓存判断是否属于自己管理
            for provider in self.providers:
                async for instruction in provider.create_result_instruction(tool_call_id, result_text, is_error):
                    yield instruction

        # --- 5. 处理生成的图片 (Images) ---
        image_data = Decode.get_image_url(mode, event)
        if image_data:
            # image_data 结构: {"image_url": {"url": "data:image/..."}}
            url = image_data.get("image_url", {}).get("url")
            if url and url.startswith("data:image"):
                async for instruction in self._handle_generated_image(url):
                    yield instruction

        # --- 6.处理 Usage ----
        usage_data = Decode.get_usage(mode, event)
        if usage_data:
            self._final_usage_data = usage_data

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

        if self._final_usage_data:
            self._usage_id = generate_uuid()
            usage_content = json.dumps(self._final_usage_data)
            yield CreateSubMessage(
                sub_message_id=self._usage_id,
                type=schemas_enums.SubMessageType.USAGE.value,
                sortOrder=99,
                status=schemas_enums.MessageStatus.COMPLETED,
                initial_content=usage_content,
                config={"context_participation_length": 0}
            )
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
