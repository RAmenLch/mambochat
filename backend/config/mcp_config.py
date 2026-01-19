from pathlib import Path

# MCP 功能全局开关
MCP_SERVER_ENABLED = True

# 路径配置
# 基于当前文件位置反向查找项目根目录
# backend/config/mcp_config.py -> backend/config -> backend -> Project Root
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent

DDGS_MCP_SERVER_PATH = _project_root / "MCP_SERVER" / "ddgs" / "search_mcp_server.py"
