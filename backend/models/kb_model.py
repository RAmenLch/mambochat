# backend/models/kb_model.py

from sqlalchemy import Column, String, Integer, TEXT, ForeignKey, DateTime, func
from backend.models.base_model import Base, generate_uuid


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

    # 关联向量表的 rowid，仅当 status 为 COMPLETED 时有效
    vector_id = Column(Integer, nullable=True)

    # 新增：切分创建时间
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 新增：向量化完成时间，用于过时判定
    processed_at = Column(DateTime, nullable=True)
