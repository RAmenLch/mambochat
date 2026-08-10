# backend/services/generation/tools/deep_builtin_tool_provider.py
#
# 【DEPRECATED - 已弃用，不再维护】
# 本文件为 DeepAgent（deepagents 库）专用内置工具提供者（UI 兼容层）。
# DeepAgent 已被淘汰，前端已无创建入口，本文件仅保留用于兼容存量数据。

from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus
)
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.models.base_model import generate_uuid


class DeepAgentBuiltinToolProvider(BaseToolProvider):
    """
    【DEPRECATED - 已弃用，不再维护】DeepAgent 内置工具提供者 (UI 兼容层)。
    拦截 DeepAgent 底层隐式注入的内置系统工具调用，并将其转换为前端可渲染的 UI 消息指令。
    复用现有的 MCP_TOOL 子消息类型，使前端能够无缝展示文件操作、终端执行等进度。
    """

    # DeepAgent 核心库内置的工具名称集合
    BUILTIN_TOOLS = {
        "read_file",
        "write_file",
        "edit_file",
        "ls",
        "glob",
        "grep",
        "execute",
        "write_todos",
        "task",
        "tree"
    }

    def __init__(self):
        # 状态映射：tool_call_id -> sub_message_id
        self._tool_sub_msg_map: Dict[str, str] = {}
        # 工具信息缓存：tool_call_id -> McpToolContent
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        # 返回空列表，因为这些工具已由 deepagents 库在底层隐式挂载，无需向上层暴露
        return []

    def get_system_prompt_injection(self) -> Optional[str]:
        # 返回空值，系统提示词由 deepagents 库自动管理
        return None

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in self.BUILTIN_TOOLS

    async def create_call_instruction(
            self,
            tool_call_id: str,
            name: str,
            arguments: Dict[str, Any],
            tool_def: Optional[BaseTool] = None
    ) -> AsyncGenerator[BaseInstruction, None]:

        # 提取 Schema (由于是内置工具，tool_def 可能为空，前端组件会自动降级渲染 arguments)
        input_schema = tool_def.args if tool_def else None

        # 复用 McpToolContent 结构，欺骗前端这是一个普通的 MCP 工具调用
        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema
        )

        # 缓存状态，建立 ID 映射
        self._tool_info_cache[tool_call_id] = tool_content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        # 生成创建子消息指令
        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=tool_content.to_json_string(),
            config=SubMessageConfig(is_minimal=True)
        )

    async def create_result_instruction(
            self,
            tool_call_id: str,
            result_text: str,
            is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:

        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        if sub_id and cached_content:
            # 更新缓存对象的状态
            cached_content.result = result_text
            cached_content.is_error = is_error

            # 发送全量更新指令
            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string()
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )

    def restore_state(self, tool_call_id: str, sub_message_id: str, tool_content: Any) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content

