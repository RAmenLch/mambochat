# backend/crud/mcp_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional

from backend.models.mcp_model import McpServer, McpTool
from backend.schemas.mcp import McpServerCreate, McpServerUpdate


async def create_mcp_server(db: AsyncSession, server: McpServerCreate) -> McpServer:
    """
    创建新的 MCP 服务器配置。
    """
    db_server = McpServer(
        name=server.name,
        description=server.description,
        transportType=server.transportType.value,
        command=server.command,
        args=server.args,
        env=server.env,
        url=str(server.url) if server.url else None,
        isEnabled=server.isEnabled
    )
    db.add(db_server)
    await db.commit()
    await db.refresh(db_server)
    return db_server


async def get_mcp_server(db: AsyncSession, server_id: str) -> Optional[McpServer]:
    """
    根据 ID 获取 MCP 服务器配置。
    """
    result = await db.execute(select(McpServer).filter(McpServer.id == server_id))
    return result.scalar_one_or_none()


async def get_all_mcp_servers(db: AsyncSession) -> List[McpServer]:
    """
    获取所有 MCP 服务器配置。
    """
    result = await db.execute(select(McpServer))
    return list(result.scalars().all())


async def get_enabled_mcp_servers(db: AsyncSession) -> List[McpServer]:
    """
    获取所有已启用的 MCP 服务器配置。
    """
    result = await db.execute(select(McpServer).filter(McpServer.isEnabled == True))
    return list(result.scalars().all())


async def update_mcp_server(db: AsyncSession, server_id: str, update_data: McpServerUpdate) -> Optional[McpServer]:
    """
    更新 MCP 服务器配置。
    """
    db_server = await get_mcp_server(db, server_id)
    if not db_server:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)

    for key, value in update_dict.items():
        if key == 'transportType' and value:
            setattr(db_server, key, value.value)
        elif key == 'url' and value:
            setattr(db_server, key, str(value))
        else:
            setattr(db_server, key, value)

    await db.commit()
    await db.refresh(db_server)
    return db_server


async def delete_mcp_server(db: AsyncSession, server_id: str) -> bool:
    """
    删除 MCP 服务器配置及关联的工具元数据。
    """
    db_server = await get_mcp_server(db, server_id)
    if not db_server:
        return False

    await db.execute(delete(McpTool).where(McpTool.server_id == server_id))

    await db.delete(db_server)
    await db.commit()
    return True

