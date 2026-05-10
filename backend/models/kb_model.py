# backend/models/kb_model.py

from sqlalchemy import Column, String, Integer, TEXT, ForeignKey, DateTime, func
from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class ResourceKBChunk(Base):
    """
    模型，用于存储知识库文件的切片文本及处理状态。
    """
    __tablename__ = "ResourceKBChunk"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    resource_id = Column(String(36), ForeignKey("Resource.id"), nullable=False, index=True)

    content = Column(TEXT, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False, default=0)

    # 状态: PENDING, COMPLETED, FAILED
    status = Column(String(20), nullable=False, default="PENDING", index=True)

    # 向量化失败的具体原因（仅 FAILED 时有值）
    error_message = Column(TEXT, nullable=True)

    # 关联向量表的 rowid，仅当 status 为 COMPLETED 时有效
    vector_id = Column(Integer, nullable=True)

    # 关联 FTS5 表的 rowid，仅当 status 为 COMPLETED 时有效
    fts_id = Column(Integer, nullable=True, index=True)

    # 切分创建时间
    created_at = Column(DateTime, nullable=False, default=get_configured_now)

    # 向量化完成时间，用于过时判定
    processed_at = Column(DateTime, nullable=True)
