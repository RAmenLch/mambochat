# backend/crud/mcp_tool_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any

from backend.models.mcp_model import McpTool
from backend.schemas.mcp import McpToolUpdate
from backend.config.timezone_config import get_configured_now


async def get_tools_by_server_id(db: AsyncSession, server_id: str) -> List[McpTool]:
    """
    获取指定 MCP 服务器下的所有工具配置。
    """
    result = await db.execute(select(McpTool).filter(McpTool.server_id == server_id))
    return list(result.scalars().all())


async def get_tool_by_id(db: AsyncSession, tool_id: str) -> Optional[McpTool]:
    """
    根据 ID 获取单个工具配置。
    """
    result = await db.execute(select(McpTool).filter(McpTool.id == tool_id))
    return result.scalar_one_or_none()


async def update_tool_config(db: AsyncSession, tool_id: str, update_data: McpToolUpdate) -> Optional[McpTool]:
    """
    更新工具的用户配置选项（启停状态、审核模式）。
    """
    db_tool = await get_tool_by_id(db, tool_id)
    if not db_tool:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)

    for key, value in update_dict.items():
        if key == 'review_mode' and value:
            setattr(db_tool, key, value.value)
        else:
            setattr(db_tool, key, value)

    await db.commit()
    await db.refresh(db_tool)
    return db_tool


async def delete_tool_if_offline(db: AsyncSession, tool_id: str) -> bool:
    """
    删除工具配置。仅允许删除状态为 offline 的工具。
    返回 True 表示删除成功，False 表示工具不存在或状态为 online 拒绝删除。
    """
    db_tool = await get_tool_by_id(db, tool_id)
    if not db_tool:
        return False

    if db_tool.status == "online":
        return False

    await db.delete(db_tool)
    await db.commit()
    return True


async def sync_tools_for_server(
        db: AsyncSession,
        server_id: str,
        latest_tools: List[Dict[str, Any]]
) -> None:
    """
    将 MCP 服务端返回的最新工具列表同步到数据库。
    包含新增、更新元数据以及标记失效工具的逻辑。
    """
    now = get_configured_now()

    # 1. 获取数据库中现有的工具
    existing_tools = await get_tools_by_server_id(db, server_id)
    existing_map = {tool.name: tool for tool in existing_tools}

    latest_names = set()

    # 2. 处理新增和更新
    for tool_data in latest_tools:
        name = tool_data.get("name")
        if not name:
            continue

        latest_names.add(name)
        description = tool_data.get("description")
        input_schema = tool_data.get("input_schema")

        if name in existing_map:
            # 更新已存在的工具元数据，并恢复 online 状态
            db_tool = existing_map[name]
            db_tool.description = description
            db_tool.input_schema = input_schema
            db_tool.status = "online"
            db_tool.last_synced_at = now
        else:
            # 插入新发现的工具
            new_tool = McpTool(
                server_id=server_id,
                name=name,
                description=description,
                input_schema=input_schema,
                status="online",
                last_synced_at=now
            )
            db.add(new_tool)

    # 3. 处理失效的工具 (数据库中有，但最新列表中没有)
    for db_tool in existing_tools:
        if db_tool.name not in latest_names:
            db_tool.status = "offline"

    await db.commit()
