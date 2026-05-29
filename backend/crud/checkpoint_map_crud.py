# backend/crud/checkpoint_map_crud.py

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from backend.models.checkpoint_map_model import MessageCheckpointMap
from backend.config.timezone_config import get_configured_now


async def get_checkpoint_id(db: AsyncSession, message_id: str) -> Optional[str]:
    """查询某个 message 对应的 checkpoint_id。"""
    result = await db.execute(
        select(MessageCheckpointMap.checkpoint_id).where(
            MessageCheckpointMap.message_id == message_id
        )
    )
    row = result.first()
    return row[0] if row else None


async def set_checkpoint_id(
    db: AsyncSession, message_id: str, checkpoint_id: str, chat_id: str
) -> None:
    """插入或更新 message → checkpoint_id 映射（upsert）。"""
    stmt = sqlite_upsert(MessageCheckpointMap).values(
        message_id=message_id,
        checkpoint_id=checkpoint_id,
        chat_id=chat_id,
        created_at=get_configured_now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[MessageCheckpointMap.message_id],
        set_={
            "checkpoint_id": stmt.excluded.checkpoint_id,
            "created_at": stmt.excluded.created_at,
        },
    )
    await db.execute(stmt)
    await db.commit()
