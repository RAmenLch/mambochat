# backend/config/internal_mcp.py

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.schemas.enums import McpTransportType

# 路径配置
# 基于当前文件位置反向查找项目根目录
# backend/config/internal_mcp.py -> backend/config -> backend -> Project Root
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent

# 定义内置 MCP 服务器的配置注册表
# Key: 系统唯一的 MCP ID (建议以 'system-' 开头)
# Value: 配置字典
INTERNAL_MCP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "system-ddgs-search": {
        "name": "⚡️联网搜索(DDGS)",
        "description": "系统内置：使用 DuckDuckGo进行联网搜索。",
        "transportType": McpTransportType.STDIO,
        "command": sys.executable,  # 使用当前运行环境的 Python 解释器
        "args": [str(_project_root / "MCP_SERVER" / "ddgs" / "search_mcp_server.py")],
        "env": {},
        "isEnabled": True
    }
}

def get_internal_mcp_config(mcp_id: str) -> Optional[Dict[str, Any]]:
    """根据 ID 获取内置 MCP 配置"""
    return INTERNAL_MCP_REGISTRY.get(mcp_id)

def list_internal_mcps() -> List[Dict[str, Any]]:
    """返回所有内置 MCP 配置的列表，并注入 ID 和 isSystem 标记"""
    results = []
    for mcp_id, config in INTERNAL_MCP_REGISTRY.items():
        item = config.copy()
        item["id"] = mcp_id
        item["isSystem"] = True
        results.append(item)
    return results
