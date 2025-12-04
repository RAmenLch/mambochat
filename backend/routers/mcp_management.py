# backend/routers/mcp_management.py

from fastapi import APIRouter
from typing import List, Dict, Any

router = APIRouter()

@router.get("/available", response_model=List[Dict[str, Any]], summary="获取可用的 MCP 服务列表")
async def get_available_mcp_servers():
    """
    返回当前系统支持的 MCP 服务列表。
    目前仅支持 Bing 搜索，返回硬编码的列表数据。
    """
    return [
        {
            "id": "bing-search",
            "name": "Bing Search",
            "description": "使用 Bing 搜索引擎获取实时网络信息。",
            "is_active": True
        }
    ]
