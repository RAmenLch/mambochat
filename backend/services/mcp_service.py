# backend/services/mcp_service.py

import sys
import os
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack
from sqlalchemy.ext.asyncio import AsyncSession

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.crud import mcp_crud
from backend.config.internal_mcp import get_internal_mcp_config, list_internal_mcps
from backend.schemas.mcp import McpServerResponse


# --- Configuration Management Services ---

async def load_mcp_config_by_id(db: AsyncSession, mcp_id: str) -> Optional[McpServerResponse]:
    """
    统一配置加载器：
    先检查是否为系统内置 ID，如果是则直接返回配置；
    否则去数据库查询。
    """
    # 1. 检查内置注册表
    internal_config = get_internal_mcp_config(mcp_id)
    if internal_config:
        # 构造响应对象
        return McpServerResponse(
            id=mcp_id,
            **internal_config,
            isSystem=True
        )

    # 2. 检查数据库
    db_server = await mcp_crud.get_mcp_server(db, mcp_id)
    if db_server:
        return McpServerResponse.model_validate(db_server)

    return None


async def get_all_merged_mcp_configs(db: AsyncSession) -> List[McpServerResponse]:
    """
    获取所有 MCP 配置的合并列表。
    合并策略：系统内置 MCP (置顶) + 数据库自定义 MCP。
    """
    response_list = []

    # 1. 获取系统内置 MCP
    internal_servers = list_internal_mcps()
    for internal in internal_servers:
        sys_mcp = McpServerResponse(
            id=internal["id"],
            name=internal["name"],
            description=internal["description"],
            transportType=internal["transportType"],
            command=str(internal["command"]) if internal.get("command") else None,
            args=internal["args"],
            env=internal["env"],
            url=internal.get("url"),
            isEnabled=internal["isEnabled"],
            isSystem=True
        )
        response_list.append(sys_mcp)

    # 2. 获取数据库中的自定义 MCP
    db_servers = await mcp_crud.get_all_mcp_servers(db)
    for server in db_servers:
        response_list.append(McpServerResponse.model_validate(server))

    return response_list
