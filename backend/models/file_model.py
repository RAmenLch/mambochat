# backend/models/file_model.py

from sqlalchemy import Column, String, Integer, DateTime, func
from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class File(Base):
    """
    模型，用于存储上传文件的元数据。
    """
    __tablename__ = "File"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)

    # management_type 值域参考 FileManagementType 枚举 (e.g., 'temporary', 'sub_message', 'resource')
    management_type = Column(String(50), nullable=False, index=True)

    created_at = Column(DateTime, nullable=False, default=get_configured_now)
