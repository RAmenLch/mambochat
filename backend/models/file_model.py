# backend/models/file_model.py

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class File(Base):
    """
    模型，用于存储上传文件的元数据。
    management_type 存储为一个 JSON 数组，支持多种类型共存。
    引入双引擎混合存储机制，支持本地磁盘与数据库纯文本存储。
    """
    __tablename__ = "File"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)

    # --- 新增字段：双引擎混合存储 ---
    # 标识文件的存储介质。枚举值为 'local' (本地文件系统) 和 'db' (数据库直接存储)
    storage_type = Column(String(20), nullable=False, default='local')

    # 仅当 storage_type='db' 时，存储文件的纯文本内容
    content = Column(Text, nullable=True)

    # management_type 现在是一个 JSON 数组，存储多个类型
    # 例如: ["temporary"], ["sub_message", "resource"]
    management_type = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, nullable=False, default=get_configured_now)

