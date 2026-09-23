# backend/services/deepseek_file_service.py
"""DeepSeek Files API 上传缓存服务。

自管数据库会话（与 log_service / cleanup_service 同风格），供模型层
``deepseek_chat_model.py`` 查询/写入图片上传结果。仅负责持久化，不涉及网络上传。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from backend.database import AsyncSessionLocal
from backend.crud import deepseek_file_crud
from backend.config.timezone_config import TZ, get_configured_now

logger = logging.getLogger(__name__)

#: DeepSeek Files API 文件有效期上限（30 天），上传时按此设置 expires_after。
FILE_TTL_SECONDS = 30 * 24 * 3600


async def get_valid_file_id(
    provider_key: str, sha256: str
) -> Optional[Tuple[str, datetime]]:
    """返回未过期的 ``(file_id, expires_at)``；无记录 / 已过期 / 失败均返回 None。"""
    try:
        async with AsyncSessionLocal() as db:
            row = await deepseek_file_crud.get_by_provider_hash(db, provider_key, sha256)
    except Exception as e:  # 缓存查询失败不应阻断生成
        logger.warning(f"[deepseek-files] 查询上传缓存失败: {e}")
        return None

    if row is None or row.status != "ready" or not row.fileId or row.expiresAt is None:
        return None

    expires_at = row.expiresAt
    if expires_at.tzinfo is None:
        expires_at = TZ.localize(expires_at)
    if expires_at <= get_configured_now():
        return None

    return row.fileId, expires_at


async def save_file_id(
    provider_key: str,
    sha256: str,
    file_id: str,
    mime_type: str,
    filename: str,
    size: int,
) -> Optional[datetime]:
    """写入一次成功上传的结果，返回过期时间；失败返回 None。"""
    expires_at = get_configured_now() + timedelta(seconds=FILE_TTL_SECONDS)
    try:
        async with AsyncSessionLocal() as db:
            await deepseek_file_crud.upsert(
                db, provider_key, sha256, file_id, mime_type, filename, size, expires_at
            )
    except Exception as e:
        logger.warning(f"[deepseek-files] 写入上传缓存失败: {e}")
        return None
    return expires_at
