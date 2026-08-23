# backend/config/internal_mcp.py

from typing import List, Dict, Any, Optional

# 定义内置 MCP 服务器的配置注册表
# Key: 系统唯一的 MCP ID (建议以 'system-' 开头)
# Value: 配置字典
#
# 注意: 联网搜索(DDGS) 已内化为 WebSearchToolProvider，
#       不再是 MCP 工具，因此从注册表中移除。
INTERNAL_MCP_REGISTRY: Dict[str, Dict[str, Any]] = {}


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
