# backend/models/mcp_model.py

from sqlalchemy import Column, String, Boolean, JSON, Text, DateTime
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

    isEnabled = Column(Boolean, default=True)

    # 状态监控字段
    last_status = Column(String(50), nullable=True)  # 例如: "healthy", "unhealthy"
    last_test_at = Column(DateTime, nullable=True)   # 上次测试/执行时间
    last_error = Column(Text, nullable=True)         # 详细报错堆栈信息
