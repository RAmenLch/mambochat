# backend/services/generation/tools/mambo_builtin_tool_provider.py

from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
)
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent
from backend.models.base_model import generate_uuid


class MamboAgentBuiltinToolProvider(BaseToolProvider):
    """
    Mambo Agent 内置工具提供者 (UI 兼容层)。

    拦截 mambo_agents 底层隐式注入的内置系统工具调用（来自 BackendToolsMiddleware
    和 SubAgentMiddleware 等），并将其转换为前端可渲染的 UI 消息指令。
    复用现有的 MCP_TOOL 子消息类型，使前端能够无缝展示文件操作、终端执行等进度。
    """

    # mambo_agents 内置工具名称集合
    # - core six: ls, read, write, edit, glob, grep (BackendToolsMiddleware)
    # - backend extras: tree, delete, execute, sandbox_run 等 (由 backend.tools 决定)
    # - workspace: copy (HybridWorkspaceBackend 跨后端复制)
    # - subagent: task (SubAgentMiddleware)
    # - async subagent: async_task, async_status (AsyncSubAgentMiddleware)
    # - planning: write_plans (MamboPlanMiddleware)
    BUILTIN_TOOLS = frozenset({
        "ls",
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "copy",
        "tree",
        "delete",
        "execute",
        "task",
        "async_task",
        "async_status",
        "write_plans",
    })

    def __init__(self):
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        return []

    def get_system_prompt_injection(self) -> Optional[str]:
        return None

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in self.BUILTIN_TOOLS

    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:

        input_schema = tool_def.args if tool_def else None

        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema,
        )

        self._tool_info_cache[tool_call_id] = tool_content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=tool_content.to_json_string(),
            config={"is_minimal": True},
        )

    async def create_result_instruction(
        self,
        tool_call_id: str,
        result_text: str,
        is_error: bool,
    ) -> AsyncGenerator[BaseInstruction, None]:

        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        if sub_id and cached_content:
            cached_content.result = result_text
            cached_content.is_error = is_error

            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string(),
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED,
            )

    def restore_state(
        self, tool_call_id: str, sub_message_id: str, tool_content: Any
    ) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
