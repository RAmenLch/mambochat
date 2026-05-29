# backend/models/checkpoint_map_model.py

from sqlalchemy import Column, String, DateTime
from backend.models.base_model import Base
from backend.config.timezone_config import get_configured_now


class MessageCheckpointMap(Base):
    """message_id → LangGraph checkpoint_id 的映射表。
    用于在消息树分支切换时定位正确的 checkpoint 分叉点。
    """
    __tablename__ = "message_checkpoints_map"

    message_id = Column(String(36), primary_key=True)
    checkpoint_id = Column(String, nullable=False)
    chat_id = Column(String(36), index=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=get_configured_now)
