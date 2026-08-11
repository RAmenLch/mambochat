# backend/crud/checkpoint_map_crud.py

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
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


async def delete_by_chat_ids(db: AsyncSession, chat_ids: List[str]) -> None:
    """删除指定会话的全部 message→checkpoint 映射。

    在会话删除时调用，避免映射表残留悬空数据。
    """
    if not chat_ids:
        return
    await db.execute(
        delete(MessageCheckpointMap).where(MessageCheckpointMap.chat_id.in_(chat_ids))
    )
    await db.commit()


async def delete_by_message_ids(db: AsyncSession, message_ids: List[str]) -> None:
    """删除指定消息的 message→checkpoint 映射。

    在消息删除时调用；被删消息已脱离 parentId 链，
    其映射不会再被分支定位查询命中，可安全清理。
    """
    if not message_ids:
        return
    await db.execute(
        delete(MessageCheckpointMap).where(MessageCheckpointMap.message_id.in_(message_ids))
    )
    await db.commit()
