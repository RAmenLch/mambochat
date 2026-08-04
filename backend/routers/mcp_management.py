# backend/routers/mcp_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.database import get_db
from backend.schemas.mcp import McpServerCreate, McpServerUpdate, McpServerResponse, McpToolResponse, McpToolUpdate
from backend.crud import mcp_crud, mcp_tool_crud
from backend.services import mcp_service
from backend.services.mcp_connection_manager import McpConnectionManager, McpConnectionError

router = APIRouter()


@router.get("/", response_model=List[McpServerResponse], summary="获取所有 MCP 服务器配置")
async def list_mcp_servers(db: AsyncSession = Depends(get_db)):
    """
    获取所有配置的 MCP 服务器。
    结果包含系统内置工具（只读）和数据库自定义工具（可编辑）。
    """
    return await mcp_service.get_all_merged_mcp_configs(db)


@router.post("/test-config", summary="测试 MCP 配置（无需保存）")
async def test_mcp_config(server: McpServerCreate):
    """
    使用传入的配置直接测试 MCP 连接，不写入数据库。
    适用于新建或编辑时在保存前验证配置是否正确。
    无论成功或失败，HTTP 状态码均为 200，请通过响应体中的 status 字段判断结果。
    """
    import uuid

    # 构建 MultiServerMCPClient 所需的配置字典
    temp_id = f"temp-test-{uuid.uuid4().hex[:8]}"

    if server.transportType.value == "stdio":
        import os
        current_env = os.environ.copy()
        if server.env:
            current_env.update(server.env)
        stdio_config = {
            "transport": "stdio",
            "command": server.command,
            "args": server.args or [],
            "env": current_env
        }
        if server.cwd:
            stdio_config["cwd"] = server.cwd
        client_config = {temp_id: stdio_config}
    else:
        http_config = {
            "transport": server.transportType.value,
            "url": server.url
        }
        if server.headers:
            http_config["headers"] = server.headers
        if server.timeout is not None:
            http_config["timeout"] = server.timeout
        if server.sse_read_timeout is not None:
            http_config["sse_read_timeout"] = server.sse_read_timeout
        client_config = {temp_id: http_config}

    try:
        tools = await McpConnectionManager.test_config(client_config)
        return {
            "status": "healthy",
            "tools_count": len(tools),
            "message": f"Successfully connected. Found {len(tools)} tools.",
            "error": None
        }
    except McpConnectionError as e:
        return {
            "status": "unhealthy",
            "tools_count": 0,
            "message": "Connection failed.",
            "error": e.error_message
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "tools_count": 0,
            "message": "Unexpected error occurred.",
            "error": str(e)
        }


@router.post("/", response_model=McpServerResponse, status_code=status.HTTP_201_CREATED,
             summary="创建新的 MCP 服务器配置")
async def create_mcp_server(
        server: McpServerCreate,
        db: AsyncSession = Depends(get_db)
):
    """
    创建自定义 MCP 服务器配置。
    """
    existing = await db.execute(select(mcp_crud.McpServer).filter_by(name=server.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="MCP server name already exists")
    return await mcp_crud.create_mcp_server(db, server)


@router.get("/{server_id}", response_model=McpServerResponse, summary="获取单个 MCP 服务器详情")
async def get_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    根据 ID 获取 MCP 服务器详情，支持系统内置 ID 和数据库 ID。
    """
    server = await mcp_service.load_mcp_config_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")
    return server


@router.put("/{server_id}", response_model=McpServerResponse, summary="更新 MCP 服务器配置")
async def update_mcp_server(
        server_id: str,
        server_update: McpServerUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新 MCP 服务器配置。
    禁止更新系统内置工具。
    """
    # 检查是否为系统内置 ID
    if server_id.startswith("system-"):
        raise HTTPException(status_code=403, detail="Cannot modify system built-in tools.")

    # 名称查重（排除自身）
    if server_update.name is not None:
        existing = await db.execute(
            select(mcp_crud.McpServer).filter(
                mcp_crud.McpServer.name == server_update.name,
                mcp_crud.McpServer.id != server_id
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="MCP server name already exists")

    updated_server = await mcp_crud.update_mcp_server(db, server_id, server_update)
    if not updated_server:
        raise HTTPException(status_code=404, detail="MCP Server not found")
    return updated_server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除 MCP 服务器配置")
async def delete_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除 MCP 服务器配置。
    禁止删除系统内置工具。
    """
    # 检查是否为系统内置 ID
    if server_id.startswith("system-"):
        raise HTTPException(status_code=403, detail="Cannot delete system built-in tools.")

    success = await mcp_crud.delete_mcp_server(db, server_id)
    if not success:
        raise HTTPException(status_code=404, detail="MCP Server not found")
    return


@router.post("/{server_id}/test", summary="测试 MCP 服务器连接")
async def test_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    测试指定的 MCP 服务器连接状态。
    无论成功或失败，HTTP 状态码均为 200，请通过响应体中的 status 字段判断结果。
    """
    # 确认服务存在
    server = await mcp_service.load_mcp_config_by_id(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    manager = McpConnectionManager(db)
    try:
        # 传递空字典作为运行时配置，仅测试基础连接
        tools = await manager.get_tools_and_check_status([server_id])
        return {
            "status": "healthy",
            "tools_count": len(tools),
            "message": f"Successfully connected. Found {len(tools)} tools.",
            "error": None
        }
    except McpConnectionError as e:
        # 捕获连接错误，返回 200 状态码和 unhealthy 状态
        return {
            "status": "unhealthy",
            "tools_count": 0,
            "message": "Connection failed.",
            "error": e.error_message
        }
    except Exception as e:
        # 捕获其他未预期的错误
        return {
            "status": "unhealthy",
            "tools_count": 0,
            "message": "Unexpected error occurred.",
            "error": str(e)
        }


@router.post("/{server_id}/sync", response_model=List[McpToolResponse], summary="同步 MCP 服务器的工具列表")
async def sync_mcp_tools(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    从 MCP 服务端获取最新工具列表，并同步到数据库中。
    """
    try:
        return await mcp_service.sync_server_tools(db, server_id)
    except McpConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{server_id}/tools", response_model=List[McpToolResponse], summary="获取 MCP 服务器的工具列表")
async def get_mcp_tools(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取指定 MCP 服务器下已同步的工具列表。
    """
    tools = await mcp_tool_crud.get_tools_by_server_id(db, server_id)
    return tools


@router.patch("/tools/{tool_id}", response_model=McpToolResponse, summary="更新 MCP 工具配置")
async def update_mcp_tool(
        tool_id: str,
        tool_update: McpToolUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新工具的启停状态与审核配置。
    """
    updated_tool = await mcp_tool_crud.update_tool_config(db, tool_id, tool_update)
    if not updated_tool:
        raise HTTPException(status_code=404, detail="MCP Tool not found")
    return updated_tool


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除失效的 MCP 工具")
async def delete_mcp_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除失效的工具记录。仅允许删除状态为 offline 的工具。
    """
    success = await mcp_tool_crud.delete_tool_if_offline(db, tool_id)
    if not success:
        raise HTTPException(status_code=400, detail="Tool not found or status is not offline. Only offline tools can be deleted.")
    return

