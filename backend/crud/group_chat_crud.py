# backend/crud/group_chat_crud.py

"""
群组会话基础数据访问层。

约定：本模块的写操作只 flush，不自行 commit；事务边界由上层服务持有，
以便建群、邮箱提交等操作在单个事务中保持原子性。
"""

from typing import List, Optional, Sequence

from sqlalchemy import select, func, update, delete, and_, or_, false
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import chat_model, group_chat_model
from backend.schemas.enums import GroupMailState, GroupTaskState
from backend.config.timezone_config import get_configured_now


# --- 群父节点与成员 ---

async def get_group_chat(db: AsyncSession, group_id: str) -> Optional[chat_model.Chat]:
    """获取群父节点（folderType=group）。"""
    result = await db.execute(
        select(chat_model.Chat).filter(
            chat_model.Chat.id == group_id,
            chat_model.Chat.itemType == "folder",
            chat_model.Chat.folderType == "group",
        )
    )
    return result.scalars().first()


async def list_member_chats(db: AsyncSession, group_id: str) -> List[chat_model.Chat]:
    """按 sortOrder、id 顺序返回群成员子会话。"""
    result = await db.execute(
        select(chat_model.Chat)
        .filter(chat_model.Chat.parentId == group_id)
        .order_by(chat_model.Chat.sortOrder.asc(), chat_model.Chat.id.asc())
    )
    return list(result.scalars().all())


async def find_member_by_alias(
    db: AsyncSession, group_id: str, alias: str
) -> Optional[chat_model.Chat]:
    """按规范化别名精确查找群成员（区分大小写）。"""
    result = await db.execute(
        select(chat_model.Chat).filter(
            chat_model.Chat.parentId == group_id,
            chat_model.Chat.memberAlias == alias,
        )
    )
    return result.scalars().first()


# --- GroupState ---

async def get_group_state(db: AsyncSession, group_id: str) -> Optional[group_chat_model.GroupState]:
    return await db.get(group_chat_model.GroupState, group_id)


# --- GroupTask ---

async def get_task(db: AsyncSession, task_id: str) -> Optional[group_chat_model.GroupTask]:
    return await db.get(group_chat_model.GroupTask, task_id)


async def list_tasks_by_state(
    db: AsyncSession, group_id: str, states: Sequence[str]
) -> List[group_chat_model.GroupTask]:
    result = await db.execute(
        select(group_chat_model.GroupTask)
        .filter(
            group_chat_model.GroupTask.groupId == group_id,
            group_chat_model.GroupTask.state.in_(list(states)),
        )
        .order_by(group_chat_model.GroupTask.sequence.asc())
    )
    return list(result.scalars().all())


# --- GroupMail ---

async def get_mail(db: AsyncSession, mail_id: str) -> Optional[group_chat_model.GroupMail]:
    return await db.get(group_chat_model.GroupMail, mail_id)


async def list_sent_mail_page(
    db: AsyncSession,
    group_id: str,
    after_sequence: Optional[int],
    limit: int,
    sender_aliases: Optional[Sequence[str]] = None,
    recipient_chat_ids: Optional[Sequence[str]] = None,
    combine: str = "union",
) -> List[group_chat_model.GroupMail]:
    """
    按已投递邮件的 sequence 游标分页（含游标之后，升序）。
    可按发信人 / 收信人过滤：
    - sender_aliases：None 表示不启用发信人筛选（非 None 且为空表示启用但无匹配）。
    - recipient_chat_ids：None 表示不启用收信人筛选（非 None 且为空表示启用但无匹配）。
    - combine：'union'=并集（满足任一条件），'intersection'=交集（同时满足）。
    """
    stmt = select(group_chat_model.GroupMail).filter(
        group_chat_model.GroupMail.groupId == group_id,
        group_chat_model.GroupMail.state == GroupMailState.SENT.value,
    )

    conds = []
    if sender_aliases is not None:
        conds.append(
            group_chat_model.GroupMail.senderAliasSnapshot.in_(list(sender_aliases))
            if sender_aliases
            else false()
        )
    if recipient_chat_ids is not None:
        if recipient_chat_ids:
            receipt_mail_ids = select(group_chat_model.GroupMailReceipt.mailId).filter(
                group_chat_model.GroupMailReceipt.recipientChatId.in_(list(recipient_chat_ids))
            )
            conds.append(group_chat_model.GroupMail.id.in_(receipt_mail_ids))
        else:
            conds.append(false())
    if conds:
        stmt = stmt.filter(or_(*conds) if combine == "union" else and_(*conds))

    if after_sequence is not None:
        stmt = stmt.filter(group_chat_model.GroupMail.sequence > after_sequence)
    stmt = stmt.order_by(group_chat_model.GroupMail.sequence.asc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_unread_receipts(
    db: AsyncSession, recipient_chat_id: str
) -> List[group_chat_model.GroupMailReceipt]:
    result = await db.execute(
        select(group_chat_model.GroupMailReceipt).filter(
            group_chat_model.GroupMailReceipt.recipientChatId == recipient_chat_id,
            group_chat_model.GroupMailReceipt.readAt.is_(None),
        )
    )
    return list(result.scalars().all())
