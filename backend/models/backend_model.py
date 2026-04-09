from sqlalchemy import Column, String, TEXT, JSON, DateTime
from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class BackendConfig(Base):
    """通用 Backend 配置表"""
    __tablename__ = "BackendConfig"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(TEXT, nullable=True)

    backendType = Column(String(50), nullable=False)
    configData = Column(JSON, nullable=False)
    tools_config = Column(JSON, nullable=True, default=lambda: {
        "execute": {"enabled": False, "require_review": True}
    })

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    updatedAt = Column(DateTime, nullable=False, default=get_configured_now, onupdate=get_configured_now)
