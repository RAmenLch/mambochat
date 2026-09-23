# backend/crud/deepseek_file_crud.py

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import deepseek_file_model


async def get_by_provider_hash(
    db: AsyncSession, provider_key: str, sha256: str
) -> Optional[deepseek_file_model.DeepSeekFileCache]:
    """按 (providerKey, sha256) 获取缓存记录。"""
    stmt = select(deepseek_file_model.DeepSeekFileCache).filter(
        deepseek_file_model.DeepSeekFileCache.providerKey == provider_key,
        deepseek_file_model.DeepSeekFileCache.sha256 == sha256,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def upsert(
    db: AsyncSession,
    provider_key: str,
    sha256: str,
    file_id: str,
    mime_type: str,
    filename: str,
    size: int,
    expires_at: datetime,
    status: str = "ready",
) -> deepseek_file_model.DeepSeekFileCache:
    """插入或更新一条上传缓存记录。"""
    row = await get_by_provider_hash(db, provider_key, sha256)
    if row is None:
        row = deepseek_file_model.DeepSeekFileCache(
            providerKey=provider_key,
            sha256=sha256,
            fileId=file_id,
            mimeType=mime_type,
            filename=filename,
            size=size,
            status=status,
            expiresAt=expires_at,
        )
        db.add(row)
    else:
        row.fileId = file_id
        row.mimeType = mime_type
        row.filename = filename
        row.size = size
        row.status = status
        row.expiresAt = expires_at
    await db.commit()
    await db.refresh(row)
    return row
