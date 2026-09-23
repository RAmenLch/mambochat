# backend/models/deepseek_file_model.py

from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint

from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now


class DeepSeekFileCache(Base):
    """DeepSeek Files API 上传缓存。

    以 ``(providerKey, sha256)`` 唯一标识一张图片的上传结果：

    - ``sha256``：图片原始字节的哈希，同一张图只需上传一次；
    - ``providerKey``：``api_base + api_key`` 的哈希，用于隔离不同 API key —— DeepSeek
      的文件归属于上传它的 key，跨 key 复用 ``file_id`` 会失效。

    ``expiresAt`` 记录 DeepSeek 侧的 30 天有效期，过期后需重新上传并更新本行。
    """

    __tablename__ = "DeepSeekFileCache"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    providerKey = Column(String(64), nullable=False)
    sha256 = Column(String(64), nullable=False)
    fileId = Column(String(128), nullable=False)
    mimeType = Column(String(100), nullable=False)
    filename = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="ready")
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    expiresAt = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("providerKey", "sha256", name="uq_dsf_provider_hash"),
    )
