"""尾部通用工具 ``tail_tool`` 的 UI 追踪 provider。

模型**在正文中**误调用 ``tail_tool`` 时,该调用会产生 graph 的 tools 节点事件;
若不为它落库,下一轮上下文从 DB 重建时会丢掉这条调用,导致其**之后的内容前缀变化、
缓存失效**。本 provider 复用 ``MCP_TOOL`` 子消息类型把 ``tail_tool`` 的调用/结果落库,
使上下文重建时能还原这条调用(与 MCP 工具的追踪方式一致)。

不加载工具(``get_tools()`` → ``[]``)——工具实例由 ``TailToolMiddleware`` 提供。
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.tools import BaseTool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
)
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.models.base_model import generate_uuid

#: 与 ``tail_tool_middleware.TAIL_TOOL_NAME`` 保持一致。
TAIL_TOOL_NAME = "tail_tool"


class TailToolProvider(BaseToolProvider):
    """把 ``tail_tool`` 的调用/结果落成 ``MCP_TOOL`` 子消息。"""

    def __init__(self) -> None:
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    # ------------------------------------------------------------------
    # BaseToolProvider
    # ------------------------------------------------------------------

    async def get_tools(self) -> List[BaseTool]:
        return []

    def get_system_prompt_injection(self) -> Optional[str]:
        return None

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name == TAIL_TOOL_NAME

    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None,
        run_uuid: Optional[str] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=tool_def.args if tool_def else None,
            run_uuid=run_uuid,
        )
        self._tool_info_cache[tool_call_id] = content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=content.to_json_string(),
            config=SubMessageConfig(is_minimal=True),
        )

    async def create_result_instruction(
        self,
        tool_call_id: str,
        result_text: str,
        is_error: bool,
        media: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached = self._tool_info_cache.get(tool_call_id)
        if not sub_id or not cached:
            return

        if not is_error and isinstance(result_text, str):
            try:
                parsed = json.loads(result_text)
                if isinstance(parsed, dict) and parsed.get("is_error"):
                    is_error = True
            except (json.JSONDecodeError, TypeError):
                pass

        cached.result = result_text
        cached.is_error = is_error

        yield UpdateSubMessageContent(
            sub_message_id=sub_id,
            content=cached.to_json_string(),
        )
        yield UpdateSubMessageStatus(
            sub_message_id=sub_id,
            status=schemas_enums.MessageStatus.COMPLETED,
        )

    def restore_state(self, tool_call_id: str, sub_message_id: str, tool_content: Any) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
