# backend/services/generation/react_manager.py
import asyncio
import json
import traceback
from types import SimpleNamespace
from typing import AsyncGenerator, List, Dict, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.abstract_manager import AbstractGenerateManager
from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    UpdateSubMessageContent,
    SetFinalStatus
)
from backend.services.generation.llm_io import WorkerOutput
from backend.schemas import enums as schemas_enums
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
        self._current_turn_tool_calls: List[Dict] = []
        # 工具调用 ID 到 SubMessage ID 的映射，用于后续更新执行结果
        self._tool_sub_msg_map: Dict[str, str] = {}

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
            # 1. 准备初始上下文
            db_chat, history_messages = await self._prepare_context(chat_id, assistant_message_id)

            # 2. 初始化 MCP 服务
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
                # 目前仅支持单一 Bing MCP Server，未来可根据 IDs 动态加载
                mcp_service = McpClientService(str(BING_MCP_SERVER_PATH))
                await mcp_service.connect()
                openai_tools = await mcp_service.get_openai_tools()

            # 3. ReAct 循环
            current_history = list(history_messages)

            # 用于在循环中累积当前 Assistant 消息的生成内容，以便在下一轮作为上下文
            current_assistant_content_buffer = []

            # 循环计数器，防止无限循环
            loop_count = 0
            MAX_LOOPS = 10

            while loop_count < MAX_LOOPS:
                # 在每轮 ReAct 循环开始前检查取消
                if await stream_manager.is_cancellation_requested(assistant_message_id):
                    raise asyncio.CancelledError("Generation was cancelled by user request.")

                loop_count += 1

                # 准备 LLM 输入
                llm_input = await self._prepare_llm_input(db_chat, current_history)

                # 注入工具
                if openai_tools:
                    llm_input.tools = openai_tools
                    # llm_input.tool_choice = "auto" # 默认通常是 auto

                # 生成
                worker_output_generator = worker.generate(llm_input)

                # 重置本轮工具调用缓存
                self._current_turn_tool_calls = []

                async for output in worker_output_generator:
                    # 在流式接收过程中检查取消
                    if await stream_manager.is_cancellation_requested(assistant_message_id):
                        raise asyncio.CancelledError("Generation was cancelled by user request.")

                    # 翻译指令并 Yield
                    async for instruction in self._translate_worker_output_to_instructions(output):
                        yield instruction

                    # 累积内容用于上下文回填
                    if output.type == "content" and output.content:
                        current_assistant_content_buffer.append(output.content)

                # 检查是否有工具调用需要执行
                if not self._current_turn_tool_calls:
                    # 没有工具调用，生成结束
                    break

                    # --- 执行阶段 (Acting) ---

                # 1. 执行工具并更新 SubMessage
                current_turn_executed_tools = []

                for tool_item in self._current_turn_tool_calls:
                    # 在执行每个工具前检查取消
                    if await stream_manager.is_cancellation_requested(assistant_message_id):
                        raise asyncio.CancelledError("Generation was cancelled by user request.")

                    tool_data = tool_item["data"]
                    tool_call_id = tool_data["tool_call_id"]
                    sub_msg_id = self._tool_sub_msg_map.get(tool_call_id)

                    try:
                        args = json.loads(tool_data["arguments"])
                        # 执行工具
                        result_str = await mcp_service.call_tool(tool_data["name"], args)
                        tool_data["result"] = result_str
                    except Exception as e:
                        tool_data["result"] = f"Error executing tool: {str(e)}"
                        tool_data["is_error"] = True

                    # 更新 SubMessage 内容和状态
                    if sub_msg_id:
                        updated_content = json.dumps(tool_data, ensure_ascii=False)
                        yield UpdateSubMessageContent(sub_message_id=sub_msg_id, content=updated_content)
                        yield UpdateSubMessageStatus(sub_message_id=sub_msg_id,
                                                     status=schemas_enums.MessageStatus.COMPLETED)

                    # 记录执行结果，用于构建上下文
                    current_turn_executed_tools.append({
                        "id": tool_call_id,
                        "data": tool_data  # 包含 result
                    })

                # 2. 更新上下文 (current_history) 以便下一轮生成

                # A. 构造上一轮的 Assistant 消息 (包含文本和工具调用请求)
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
                    # 历史记录中的 MCP_TOOL sub_message 应该包含原始调用信息
                    virtual_assistant_subs.append(SimpleNamespace(
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        content=json.dumps(tool_item["data"], ensure_ascii=False),
                        config={},
                        sortOrder=2
                    ))

                virtual_assistant_msg = SimpleNamespace(
                    role=schemas_enums.MessageRole.ASSISTANT.value,
                    sub_messages=virtual_assistant_subs
                )
                current_history.append(virtual_assistant_msg)

                # 重置 buffer，因为下一轮是新的 Assistant 消息
                current_assistant_content_buffer = []
                # `_current_turn_tool_calls` 会在循环开始时重置

                # 继续下一轮循环...

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
                    # 构造工具调用的存储结构
                    tool_data = {
                        "tool_call_id": tool_call.get("id"),
                        "name": tool_call.get("function", {}).get("name"),
                        "arguments": tool_call.get("function", {}).get("arguments"),
                        "result": None,
                        "is_error": False
                    }
                    json_content = json.dumps(tool_data, ensure_ascii=False)

                    # 生成 ID
                    sub_id = generate_uuid()
                    self._tool_sub_msg_map[tool_data["tool_call_id"]] = sub_id

                    # 记录到内存以便后续执行 (ReAct 循环使用)
                    self._current_turn_tool_calls.append({
                        "data": tool_data,
                        "temp_ref_id": sub_id  # 这里的 key 其实用不到了，主要是 data
                    })

                    # 发出创建子消息指令
                    yield CreateSubMessage(
                        sub_message_id=sub_id,
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        sortOrder=2,  # 放在内容之后
                        status=schemas_enums.MessageStatus.GENERATING,
                        initial_content=json_content,
                        config={"is_minimal": True}
                    )

        elif output.type == "usage":
            if output.usage:
                self._final_usage_data = output.usage

        elif output.type == "done":
            # 如果本轮有工具调用，Manager 的 run 循环会继续，这里不结束整个消息
            # 仅结束当前 Content/Reasoning 分区状态
            if self._content_id:
                yield UpdateSubMessageStatus(
                    sub_message_id=self._content_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )
                # 为了支持下一轮生成新的 Content，重置 ID
                self._content_id = None

            if self._reasoning_id:
                yield UpdateSubMessageStatus(
                    sub_message_id=self._reasoning_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )
                self._reasoning_id = None

            if not self._current_turn_tool_calls:
                # 只有当没有工具调用时，才生成 Usage 和 FinalStatus
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

        # 允许子类扩展其他类型的处理（如 DefaultManager 处理 image_content）
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

        # 1. 更新活跃的 Reasoning/Content 分区状态
        # 注意：ReAct 循环中 ID 可能被重置，但这里只能尝试清理当前持有的 ID
        if self._reasoning_id:
            yield UpdateSubMessageStatus(sub_message_id=self._reasoning_id, status=final_status)
        if self._content_id:
            yield UpdateSubMessageStatus(sub_message_id=self._content_id, status=final_status)

        # 2. 更新活跃的 Tool 分区状态
        for tool_id, sub_id in self._tool_sub_msg_map.items():
            pass  # 简单跳过，不强制更新所有 Tool 状态，依赖 FinalStatus

        # 3. 展示错误信息
        if error_content:
            # 如果有正在生成的 Content，追加错误
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

