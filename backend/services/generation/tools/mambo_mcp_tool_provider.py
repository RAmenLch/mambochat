"""Mambo MCP 薄适配层 —— 仅为 MCPMiddleware 提供 MCP_TOOL UI 子消息追踪。

- 不加载工具（get_tools() → []）
- 全部透传 name / arguments / result，不篡改任何字段以保证 LLM 上下文一致性
- 同时覆盖 wrapped 模式（mcp_call_tool / mcp_get_tool_description）和
  direct 模式（server__tool）
- 支持 HITL 恢复时的状态重建
- 自包含 DB 查询：构造时传入 db + mcp_ids，调用 load_configs() 后即可通过
  属性获取 builder 阶段创建 MCPMiddleware 所需的数据
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool
from mambo_agents.middleware.mcp import MCPServerConfig, mcp_tool_name

from backend.crud import mcp_crud
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

logger = logging.getLogger(__name__)


class MamboMCPToolProvider(BaseToolProvider):
    """薄适配层：自包含 DB 查询 + UI 子消息追踪，不加载工具。

    Usage::

        provider = MamboMCPToolProvider(db, mcp_ids)
        loaded = await provider.load_configs()
        if loaded:
            agent_config.mcp_server_configs = provider.mcp_server_configs
            agent_config.mcp_exclude_tools = provider.mcp_exclude_tools
    """

    def __init__(self, db: AsyncSession, mcp_ids: List[str]) -> None:
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}
        self._mcp_tool_names: set[str] = set()

        self._db = db
        self._mcp_ids = mcp_ids
        self._server_configs: List[MCPServerConfig] = []
        self._exclude_tools: Optional[Dict[str, frozenset[str]]] = None
        self._id_to_name: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # 对外属性（load_configs 之后可用）
    # ------------------------------------------------------------------

    @property
    def mcp_server_configs(self) -> List[MCPServerConfig]:
        return self._server_configs

    @property
    def mcp_exclude_tools(self) -> Optional[Dict[str, frozenset[str]]]:
        return self._exclude_tools

    @property
    def id_to_name(self) -> Dict[str, str]:
        return self._id_to_name

    # ------------------------------------------------------------------
    # DB 配置加载
    # ------------------------------------------------------------------

    async def load_configs(self) -> bool:
        """从 DB 加载 MCP 配置。返回 True 表示有可用服务器。"""
        servers_db = await mcp_crud.get_mcp_servers_by_ids(self._db, self._mcp_ids)
        if not servers_db:
            return False

        id_to_name: dict[str, str] = {}
        server_configs: list[MCPServerConfig] = []

        for s in servers_db:
            if not s.isEnabled:
                continue
            id_to_name[s.id] = s.name
            cfg = MCPServerConfig(
                name=s.name,
                transport=s.transportType,
                command=s.command,
                args=s.args or [],
                env=s.env,
                cwd=s.cwd,
                url=s.url,
                headers=s.headers,
                timeout=s.timeout,
            )
            server_configs.append(cfg)

        if not server_configs:
            self._id_to_name = id_to_name
            return False

        all_tools = await mcp_crud.get_all_tools_by_server_ids(self._db, self._mcp_ids)
        _exclude: dict[str, set[str]] = {}
        for t in all_tools:
            if not t.is_enabled:
                sname = id_to_name.get(t.server_id)
                if sname:
                    _exclude.setdefault(sname, set()).add(t.name)
        exclude_tools = (
            {k: frozenset(v) for k, v in _exclude.items()} if _exclude else None
        )

        all_tool_names: set[str] = {"mcp_call_tool", "mcp_get_tool_description"}
        for t in all_tools:
            if t.is_enabled:
                sname = id_to_name.get(t.server_id)
                if sname:
                    all_tool_names.add(mcp_tool_name(sname, t.name))

        self._server_configs = server_configs
        self._exclude_tools = exclude_tools
        self._id_to_name = id_to_name
        self._mcp_tool_names = all_tool_names
        return True

    # ------------------------------------------------------------------
    # BaseToolProvider 接口
    # ------------------------------------------------------------------

    async def get_tools(self) -> List[BaseTool]:
        return []

    def get_system_prompt_injection(self) -> Optional[str]:
        return None

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in self._mcp_tool_names

    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=tool_def.args if tool_def else None,
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

    def restore_state(
        self, tool_call_id: str, sub_message_id: str, tool_content: Any
    ) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
