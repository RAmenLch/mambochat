# backend/models/log_model.py

from sqlalchemy import Column, String, DateTime, JSON, Index
from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class MamboPostLog(Base):
    """
    模型，用于存储发送给 LLM API 的底层报文日志
    """
    __tablename__ = "MamboPostLog"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)

    chatId = Column(String(36), nullable=True, index=True)
    messageId = Column(String(36), nullable=True, index=True)

    managerName = Column(String(100), nullable=True)
    agentName = Column(String(100), nullable=True)

    configMetaData = Column(JSON, nullable=True)
    rawPayload = Column(JSON, nullable=True)

    # 显式创建索引，createdAt 降序索引对分页查询非常重要
    __table_args__ = (
        Index('ix_mambopostlog_created_at_desc', createdAt.desc()),
    )

