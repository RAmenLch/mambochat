# backend/models/image_gen_model.py

from sqlalchemy import Column, String, Boolean, Float, Integer, TEXT, DateTime

from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class ImageGenConfig(Base):
    """生图工具配置。

    一条配置绑定一个符合生图标准（三个固定工具名）的 MCP 服务，
    并提供默认参数。Agent 通过 agentParameters.image_gen.configId 引用。
    """

    __tablename__ = "ImageGenConfig"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(TEXT, nullable=True)

    # 绑定的 MCP 服务（McpServer.id）
    mcpServerId = Column(String(36), nullable=False, index=True)

    # 默认参数
    defaultCount = Column(Integer, nullable=False, default=1)
    defaultSync = Column(Boolean, nullable=False, default=True)

    # 单次 MCP 工具调用超时（秒），None 表示沿用 MCP 服务自身配置
    timeout = Column(Float, nullable=True)

    isEnabled = Column(Boolean, default=True)

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    updatedAt = Column(DateTime, nullable=False, default=get_configured_now, onupdate=get_configured_now)
