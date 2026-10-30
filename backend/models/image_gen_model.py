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
    # 默认分辨率，形如 1024x1024（对应契约参数 resolution）
    defaultResolution = Column(String(20), nullable=False, default="1024x1024")
    # 状态工具默认阻塞等待秒数（对应契约参数 wait_timeout），0 表示不等待
    defaultWaitTimeout = Column(Integer, nullable=False, default=0)

    # 单次 MCP 工具调用超时（秒），None 表示沿用 MCP 服务自身配置
    timeout = Column(Float, nullable=True)

    # 工具集开关（两者至少开启一个）
    # enableStandardTools：契约三件套 image_generate / image_task_status / image_download
    # enableGenerateShow：平台侧一条龙 image_generate_show（生成 + 落盘 + 展示）
    enableStandardTools = Column(Boolean, nullable=False, default=True)
    enableGenerateShow = Column(Boolean, nullable=False, default=False)

    isEnabled = Column(Boolean, default=True)

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    updatedAt = Column(DateTime, nullable=False, default=get_configured_now, onupdate=get_configured_now)
