# backend/models/mcp_model.py

from sqlalchemy import Column, String, Boolean, Float, JSON, Text, DateTime
from backend.models.base_model import Base, generate_uuid
from backend.schemas.enums import McpTransportType


class McpServer(Base):
    __tablename__ = "McpServer"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # 配置类型: 'stdio' or 'sse'
    transportType = Column(String(20), nullable=False, default=McpTransportType.STDIO.value)

    # STDIO 专属配置
    command = Column(String(255), nullable=True)  # 例如: "python", "uv", "npx"
    args = Column(JSON, nullable=True)  # 例如: ["/path/to/server.py", "--verbose"]
    env = Column(JSON, nullable=True)  # 例如: {"API_KEY": "xyz"}

    # SSE 专属配置
    url = Column(String(500), nullable=True)  # 例如: "http://localhost:8000/sse"
    headers = Column(JSON, nullable=True)  # 例如: {"X-Personal-Token": "***"}
    timeout = Column(Float, nullable=True)  # HTTP 超时（秒）
    sse_read_timeout = Column(Float, nullable=True)  # SSE 读取超时（秒）

    # STDIO 专属配置
    cwd = Column(String(500), nullable=True)  # 工作目录

    # 是否使用全局代理（仅 sse/streamable_http 生效；False=直连并屏蔽环境变量代理）
    useProxy = Column(Boolean, default=False)

    isEnabled = Column(Boolean, default=True)

    # 状态监控字段
    last_status = Column(String(50), nullable=True)  # 例如: "healthy", "unhealthy"
    last_test_at = Column(DateTime, nullable=True)   # 上次测试/执行时间
    last_error = Column(Text, nullable=True)         # 详细报错堆栈信息


class McpTool(Base):
    __tablename__ = "McpTool"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    input_schema = Column(JSON, nullable=True)

    is_enabled = Column(Boolean, default=True)
    review_mode = Column(String(20), default="none")
    status = Column(String(20), default="online")
    last_synced_at = Column(DateTime, nullable=True)
