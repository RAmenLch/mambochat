# backend/routers/mcp_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.database import get_db
from backend.schemas.mcp import McpServerCreate, McpServerUpdate, McpServerResponse
from backend.crud import mcp_crud
from backend.services import mcp_service

router = APIRouter()


@router.get("/", response_model=List[McpServerResponse], summary="获取所有 MCP 服务器配置")
async def list_mcp_servers(db: AsyncSession = Depends(get_db)):
    """
    获取所有配置的 MCP 服务器。
    结果包含系统内置工具（只读）和数据库自定义工具（可编辑）。
    """
    return await mcp_service.get_all_merged_mcp_configs(db)


@router.post("/", response_model=McpServerResponse, status_code=status.HTTP_201_CREATED,
             summary="创建新的 MCP 服务器配置")
async def create_mcp_server(
        server: McpServerCreate,
        db: AsyncSession = Depends(get_db)
):
    """
    创建自定义 MCP 服务器配置。
    """
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
