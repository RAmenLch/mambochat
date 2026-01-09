# backend/services/generation/react_manager.py
import asyncio
import json
import traceback
from types import SimpleNamespace
from typing import AsyncGenerator, List, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.abstract_manager import AbstractGenerateManager
from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    UpdateSubMessageContent,
    UpdateSubMessageConfig,
    SetFinalStatus
)
from backend.services.generation.llm_io import WorkerOutput, LLMInput
from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend.schemas import enums as schemas_enums, SubMessageType
from backend.schemas.message import McpToolContent
from backend.models.base_model import generate_uuid
from backend.config.mcp_config import MCP_SERVER_ENABLED, BING_MCP_SERVER_PATH
from backend.services.mcp_service import McpClientService
from backend.services.stream_manager_service import stream_manager


class ReActAgentChatGenerateManager(AbstractGenerateManager):
    """
    ReAct 代理聊天生成管理器。
    支持 Reasoning + Acting 循环，负责处理 Tool Calls、上下文维护和多轮生成。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self._reasoning_id: Optional[str] = None
        self._content_id: Optional[str] = None
        self._usage_id: Optional[str] = None
        self._final_usage_data: Optional[Dict] = None

        # 每一轮生成的工具调用暂存
        # 列表元素结构: {"data": McpToolContent, "temp_ref_id": str}
        self._current_turn_tool_calls: List[Dict] = []
        # 工具调用 ID 到 SubMessage ID 的映射，用于后续更新执行结果
        self._tool_sub_msg_map: Dict[str, str] = {}

    def _create_builder(self, chat_id: str, assistant_message_id: str) -> LLMInputBuilder:
        """
        创建并配置 LLMInputBuilder 的辅助方法。
        集中了通用的上下文过滤和多模态配置逻辑。
        """
        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)
        (
            builder
            .slice_until_message(assistant_message_id)
            .filter_sub_message_types(SubMessageType.NORMAL, SubMessageType.MCP_TOOL, SubMessageType.FILE)
            .enable_image_with_model()
            .enable_cpl_filter()
        )
        return builder

    async def _prepare_llm_input(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> LLMInput:
        """
        实现基类抽象方法。
        注意：在 run 方法的 ReAct 循环中，我们会直接操作 builder，
        此方法主要用于满足接口契约或单次生成的场景。
        """
        builder = self._create_builder(chat_id, assistant_message_id)

        # 初次构建以加载 Chat 和配置
        llm_input = await builder.build()

        # 处理 max_context_messages
        if builder.chat and builder.chat.modelParameters:
            try:
                params = json.loads(builder.chat.modelParameters) if isinstance(builder.chat.modelParameters,
                                                                                str) else builder.chat.modelParameters
                limit = params.get('max_context_messages')
                if isinstance(limit, int) and limit > 0:
                    builder.slice(start=-limit)
                    llm_input = await builder.build()
            except (json.JSONDecodeError, TypeError):
                pass

        return llm_input

    async def run(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        重写模板方法，实现 ReAct 循环。
        """
        overall_status = schemas_enums.MessageStatus.FAILED
        mcp_service = None

        try:
            # 1. 初始化 Builder 并进行初次构建
            builder = self._create_builder(chat_id, assistant_message_id)
            llm_input = await builder.build()

            # 2. 获取 Chat 对象及配置 (Builder 已加载)
            db_chat = builder.chat

            # 3. 处理 max_context_messages
            # 注意：这将影响后续所有循环的上下文窗口
            if db_chat.modelParameters:
                try:
                    params = json.loads(db_chat.modelParameters) if isinstance(db_chat.modelParameters,
                                                                               str) else db_chat.modelParameters
                    limit = params.get('max_context_messages')
                    if isinstance(limit, int) and limit > 0:
                        builder.slice(start=-limit)
                        # 重新构建以应用切片
                        llm_input = await builder.build()
                except (json.JSONDecodeError, TypeError):
                    pass

            # 4. 初始化 MCP 服务
            enabled_mcp_ids = []
            if db_chat.modelParameters:
                try:
                    params = json.loads(db_chat.modelParameters) if isinstance(db_chat.modelParameters,
                                                                               str) else db_chat.modelParameters
                    enabled_mcp_ids = params.get("enabled_mcp_ids", [])
                except:
                    pass

            openai_tools = None
            if MCP_SERVER_ENABLED and enabled_mcp_ids:
                mcp_service = McpClientService(str(BING_MCP_SERVER_PATH))
                await mcp_service.connect()
                openai_tools = await mcp_service.get_openai_tools()

            # 5. ReAct 循环准备
            # 使用 Builder 加载的原始历史记录作为基准 (不受 slice 影响，slice 仅在 build 时应用)
            current_history = list(builder.history)

            # 用于在循环中累积当前 Assistant 消息的生成内容
            current_assistant_content_buffer = []

            loop_count = 0
            MAX_LOOPS = 10

            while loop_count < MAX_LOOPS:
                # 检查取消
                if await stream_manager.is_cancellation_requested(assistant_message_id):
                    raise asyncio.CancelledError("Generation was cancelled by user request.")

                loop_count += 1

                # 如果不是第一轮，或者历史记录发生了变化，需要更新 Builder
                if loop_count > 1:
                    builder.set_history_override(current_history)
                    llm_input = await builder.build()

                # 注入工具
                if openai_tools:
                    llm_input.tools = openai_tools

                # 生成
                worker_output_generator = worker.generate(llm_input)

                # 重置本轮工具调用缓存
                self._current_turn_tool_calls = []

                async for output in worker_output_generator:
                    if await stream_manager.is_cancellation_requested(assistant_message_id):
                        raise asyncio.CancelledError("Generation was cancelled by user request.")

                    async for instruction in self._translate_worker_output_to_instructions(output):
                        yield instruction

                    if output.type == "content" and output.content:
                        current_assistant_content_buffer.append(output.content)

                # 检查是否有工具调用需要执行
                if not self._current_turn_tool_calls:
                    break

                # --- 执行阶段 (Acting) ---

                for tool_item in self._current_turn_tool_calls:
                    if await stream_manager.is_cancellation_requested(assistant_message_id):
                        raise asyncio.CancelledError("Generation was cancelled by user request.")

                    # tool_content 是 McpToolContent 实例
                    tool_content: McpToolContent = tool_item["data"]
                    sub_msg_id = self._tool_sub_msg_map.get(tool_content.tool_call_id)

                    try:
                        args = tool_content.get_argument_dict()
                        result_str = await mcp_service.call_tool(tool_content.name, args)
                        tool_content.result = result_str
                        tool_content.is_error = False
                    except Exception as e:
                        tool_content.result = f"Error executing tool: {str(e)}"
                        tool_content.is_error = True

                    if sub_msg_id:
                        # 使用 McpToolContent 标准化序列化
                        updated_content = tool_content.to_json_string()
                        yield UpdateSubMessageContent(sub_message_id=sub_msg_id, content=updated_content)
                        yield UpdateSubMessageStatus(sub_message_id=sub_msg_id,
                                                     status=schemas_enums.MessageStatus.COMPLETED)

                # --- 上下文更新阶段 (Update Context) ---

                # 1. 构建本轮的 Assistant 消息 (包含文本内容和工具调用请求)
                assistant_content = "".join(
                    current_assistant_content_buffer) if current_assistant_content_buffer else None

                virtual_assistant_subs = []
                if assistant_content:
                    virtual_assistant_subs.append(SimpleNamespace(
                        type=schemas_enums.SubMessageType.NORMAL.value,
                        content=assistant_content,
                        config={},
                        sortOrder=1
                    ))

                for tool_item in self._current_turn_tool_calls:
                    tool_content: McpToolContent = tool_item["data"]
                    virtual_assistant_subs.append(SimpleNamespace(
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        content=tool_content.to_json_string(),
                        config={},
                        sortOrder=2
                    ))

                virtual_assistant_msg = SimpleNamespace(
                    role=schemas_enums.MessageRole.ASSISTANT.value,
                    sub_messages=virtual_assistant_subs
                )
                current_history.append(virtual_assistant_msg)

                # 2. 构建并追加本轮的 Tool 消息 (包含工具执行结果)
                # 这一步至关重要，确保下一轮 Builder 构建 Payload 时能提取到 'role': 'tool' 的消息
                for tool_item in self._current_turn_tool_calls:
                    tool_content: McpToolContent = tool_item["data"]

                    if tool_content.is_executed:
                        # 创建一个虚拟的 Tool 消息
                        # 这里 content 是结果字符串，tool_call_id 必须匹配
                        virtual_tool_msg = SimpleNamespace(
                            role="tool",
                            tool_call_id=tool_content.tool_call_id,
                            sub_messages=[
                                SimpleNamespace(
                                    type=schemas_enums.SubMessageType.NORMAL.value,
                                    content=tool_content.result,
                                    config={},
                                    sortOrder=1
                                )
                            ]
                        )
                        current_history.append(virtual_tool_msg)

                # 重置缓冲区
                current_assistant_content_buffer = []

        except (asyncio.CancelledError, Exception) as e:
            if isinstance(e, asyncio.CancelledError):
                print(f"[ReActAgentManager] Task cancelled for message '{assistant_message_id}'.")
                overall_status = schemas_enums.MessageStatus.COMPLETED
            else:
                print(f"[ReActAgentManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
                traceback.print_exc()
                overall_status = schemas_enums.MessageStatus.FAILED

            async for instruction in self._cleanup_on_exception(assistant_message_id, overall_status, e):
                yield instruction

        finally:
            if mcp_service:
                await mcp_service.close()

    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将 Worker 输出转换为指令。
        处理 Reasoning, Content, Usage, Done, ToolCall。
        """
        if output.type == "reasoning":
            if not self._reasoning_id:
                self._reasoning_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._reasoning_id,
                    type=schemas_enums.SubMessageType.REASONING.value,
                    sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
            yield AppendToSubMessage(sub_message_id=self._reasoning_id, content=output.content)

        elif output.type == "content":
            # 如果内容为空且尚未创建子消息，则跳过，避免创建空的子消息
            if not output.content and not self._content_id:
                return

            if not self._content_id:
                self._content_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._content_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
            yield AppendToSubMessage(sub_message_id=self._content_id, content=output.content)

        elif output.type == "tool_call":
            if output.tool_calls:
                for tool_call in output.tool_calls:
                    # 使用 McpToolContent 构建对象
                    tool_content = McpToolContent(
                        tool_call_id=tool_call.get("id"),
                        name=tool_call.get("function", {}).get("name"),
                        arguments=tool_call.get("function", {}).get("arguments")
                    )

                    sub_id = generate_uuid()
                    self._tool_sub_msg_map[tool_content.tool_call_id] = sub_id

                    # 存储强类型的 tool_content
                    self._current_turn_tool_calls.append({
                        "data": tool_content,
                        "temp_ref_id": sub_id
                    })

                    # 使用标准化 JSON 字符串创建子消息
                    yield CreateSubMessage(
                        sub_message_id=sub_id,
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        sortOrder=2,
                        status=schemas_enums.MessageStatus.GENERATING,
                        initial_content=tool_content.to_json_string(),
                        config={"is_minimal": True}
                    )

        elif output.type == "usage":
            if output.usage:
                self._final_usage_data = output.usage

        elif output.type == "done":
            # 判断是否还有工具需要执行（意味着这只是 ReAct 循环的一个中间步骤）
            has_pending_tools = bool(self._current_turn_tool_calls)

            if has_pending_tools:
                # 中间状态：不结束当前的 Reasoning/Content SubMessage，而是追加换行符。
                # 这样下一轮循环生成的文本会接在同一个消息气泡里。
                if self._content_id:
                    yield AppendToSubMessage(sub_message_id=self._content_id, content="\n")

                if self._reasoning_id:
                    yield AppendToSubMessage(sub_message_id=self._reasoning_id, content="\n")
            else:
                # 真正结束：没有工具要调用了，结束所有打开的 SubMessage 并发送最终状态。
                if self._content_id:
                    yield UpdateSubMessageStatus(
                        sub_message_id=self._content_id,
                        status=schemas_enums.MessageStatus.COMPLETED
                    )
                    self._content_id = None

                if self._reasoning_id:
                    # 在标记为 COMPLETED 之前，先将其标记为最小化
                    yield UpdateSubMessageConfig(
                        sub_message_id=self._reasoning_id,
                        config={"is_minimal": True}
                    )
                    yield UpdateSubMessageStatus(
                        sub_message_id=self._reasoning_id,
                        status=schemas_enums.MessageStatus.COMPLETED
                    )
                    self._reasoning_id = None

                if not self._current_turn_tool_calls:
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
                    yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            raise RuntimeError(output.content)

        else:
            async for instruction in self._handle_custom_worker_output(output):
                yield instruction

    async def _handle_custom_worker_output(self, output: WorkerOutput) -> AsyncGenerator[BaseInstruction, None]:
        """
        钩子方法：允许子类处理额外的 WorkerOutput 类型。
        """
        if False:
            yield

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        清理逻辑。
        """
        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            elif not isinstance(exception, (type(None),)):
                if "CancelledError" in str(type(exception)):
                    error_content = "生成被用户取消。"
                else:
                    error_content = f"发生未处理的异常: {str(exception)}"

        if self._reasoning_id:
            # 在标记为 COMPLETED/FAILED 之前，先将其标记为最小化
            yield UpdateSubMessageConfig(
                sub_message_id=self._reasoning_id,
                config={"is_minimal": True}
            )
            yield UpdateSubMessageStatus(sub_message_id=self._reasoning_id, status=final_status)

        if self._content_id:
            yield UpdateSubMessageStatus(sub_message_id=self._content_id, status=final_status)

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
