# backend/crud/message_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update
from typing import List, Optional
import json
from datetime import datetime, timezone

from backend.models import chat_model
from backend import schemas
from backend.models.chat_model import SubMessage
from backend.schemas.enums import MessageStatus
from backend.config.timezone_config import get_configured_now, TZ


def _safe_timestamp(dt) -> float:
    """
    安全提取时间戳，解决 SQLAlchemy 混合查询时产生的 datetime 与 str 类型不一致，
    以及 naive 与 aware datetime 比较报错的问题。
    所有数据库返回的时间（SQLite为naive）均视为配置时区时间进行转换。
    """
    if not dt:
        return 0.0
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # 数据库返回的时间不带时区，视为当前配置时区
            try:
                return TZ.localize(dt).timestamp()
            except AttributeError:
                return dt.replace(tzinfo=TZ).timestamp()
        return dt.timestamp()
    if isinstance(dt, str):
        try:
            # 兼容 SQLite 可能返回的字符串格式
            dt_str = dt.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(dt_str)
            if parsed.tzinfo is None:
                # 字符串解析为不带时区，视为当前配置时区
                try:
                    parsed = TZ.localize(parsed)
                except AttributeError:
                    parsed = parsed.replace(tzinfo=TZ)
            return parsed.timestamp()
        except ValueError:
            pass
    return 0.0


async def batch_update_sub_messages_status_optimistic(
        db: AsyncSession,
        sub_message_ids: List[str],
        old_status: MessageStatus,
        new_status: MessageStatus
) -> int:
    if not sub_message_ids:
        return 0

    stmt = (
        update(SubMessage)
        .where(SubMessage.id.in_(sub_message_ids))
        .where(SubMessage.status == old_status.value)
        .values(status=new_status.value)
    )

    result = await db.execute(stmt)
    await db.commit()

    return result.rowcount


async def get_message(db: AsyncSession, message_id: str) -> Optional[chat_model.Message]:
    result = await db.execute(
        select(chat_model.Message)
        .options(selectinload(chat_model.Message.sub_messages))
        .filter(chat_model.Message.id == message_id)
    )
    return result.scalars().first()


async def update_message(db: AsyncSession, message_id: str, message_update: schemas.MessageUpdate) -> Optional[
    chat_model.Message]:
    db_message = await get_message(db, message_id=message_id)
    if not db_message:
        return None

    for sub_message in db_message.sub_messages:
        await db.delete(sub_message)
    await db.flush()

    new_sub_messages = []
    for sub_msg_data in message_update.sub_messages:
        new_sub_msg = chat_model.SubMessage(
            messageId=db_message.id,
            content=sub_msg_data.content,
            sortOrder=sub_msg_data.sortOrder,
            type=sub_msg_data.type,
            status=sub_msg_data.status.value,
            config=sub_msg_data.config.model_dump_json()
        )
        new_sub_messages.append(new_sub_msg)

    db.add_all(new_sub_messages)
    await db.commit()
    await db.refresh(db_message)
    return db_message


async def _get_active_linear_path(db: AsyncSession, chat_id: str) -> List[chat_model.Message]:
    result = await db.execute(
        select(chat_model.Message)
        .options(selectinload(chat_model.Message.sub_messages))
        .filter(chat_model.Message.chatId == chat_id)
    )
    all_messages = result.scalars().all()

    parent_map = {}
    for msg in all_messages:
        parent_map.setdefault(msg.parentId, []).append(msg)

    # 使用 _safe_timestamp 避免类型冲突
    for pid in parent_map:
        parent_map[pid].sort(key=lambda x: _safe_timestamp(x.createdAt))

    active_list = []
    roots = parent_map.get(None, [])
    if not roots:
        return active_list

    # 使用 _safe_timestamp
    current = max(roots, key=lambda x: _safe_timestamp(x.lastActiveAt))

    while current:
        siblings = parent_map.get(current.parentId, [])
        setattr(current, 'sibling_ids', [s.id for s in siblings])
        if current in siblings:
            setattr(current, 'sibling_index', siblings.index(current))
        else:
            setattr(current, 'sibling_index', 0)

        active_list.append(current)

        children = parent_map.get(current.id, [])
        if not children:
            break

        # 使用 _safe_timestamp
        max_child = max(children, key=lambda x: _safe_timestamp(x.lastActiveAt))

        curr_time = _safe_timestamp(current.lastActiveAt)
        child_time = _safe_timestamp(max_child.lastActiveAt)

        # 容差 0.1 秒，防止相同事务内微小精度差异
        if curr_time - child_time > 0.1:
            break

        current = max_child

    return active_list


async def get_messages_by_chat(db: AsyncSession, chat_id: str, skip: int = 0, limit: Optional[int] = None) -> List[
    chat_model.Message]:
    active_list = await _get_active_linear_path(db, chat_id)

    if limit is not None:
        return active_list[skip: skip + limit]
    return active_list[skip:]


async def get_limited_recent_messages(db: AsyncSession, chat_id: str, limit: int) -> List[chat_model.Message]:
    active_list = await _get_active_linear_path(db, chat_id)
    return active_list[-limit:] if limit > 0 else []


async def create_message(db: AsyncSession, message: schemas.MessageCreate, chat_id: str) -> chat_model.Message:
    active_list = await _get_active_linear_path(db, chat_id)

    if "parentId" not in message.model_fields_set:
        parent_id = active_list[-1].id if active_list else None
    else:
        parent_id = message.parentId

    sort_order = 1
    if parent_id:
        parent_msg = await db.get(chat_model.Message, parent_id)
        if parent_msg:
            sort_order = parent_msg.sortOrder + 1

    now = get_configured_now()

    db_message = chat_model.Message(
        role=message.role,
        chatId=chat_id,
        parentId=parent_id,
        sortOrder=sort_order,
        lastActiveAt=now
    )
    db.add(db_message)
    await db.flush()

    for sub_msg_data in message.sub_messages:
        db_sub_message = chat_model.SubMessage(
            messageId=db_message.id,
            content=sub_msg_data.content,
            sortOrder=sub_msg_data.sortOrder,
            type=sub_msg_data.type,
            status=sub_msg_data.status.value,
            config=sub_msg_data.config.model_dump_json()
        )
        db.add(db_sub_message)

    # --- 核心修复：同步更新所有祖先的 lastActiveAt ---
    if parent_id:
        ancestor_ids = set()

        # 优先尝试从已加载的 active_list 中提取祖先，避免额外查库
        parent_index = -1
        for i, msg in enumerate(active_list):
            if msg.id == parent_id:
                parent_index = i
                break

        if parent_index != -1:
            ancestor_ids = {msg.id for msg in active_list[:parent_index + 1]}
        else:
            # 如果 parent_id 不在 active_list 中，退化为全量查库回溯
            result = await db.execute(
                select(chat_model.Message.id, chat_model.Message.parentId).filter(chat_model.Message.chatId == chat_id))
            all_msgs = result.all()
            parent_map = {row.id: row.parentId for row in all_msgs}

            curr = parent_id
            while curr:
                ancestor_ids.add(curr)
                curr = parent_map.get(curr)

        if ancestor_ids:
            await db.execute(
                update(chat_model.Message)
                .where(chat_model.Message.id.in_(ancestor_ids))
                .values(lastActiveAt=now)
            )

    await db.commit()
    await db.refresh(db_message, ['sub_messages'])
    return db_message


async def delete_message(db: AsyncSession, message_id: str) -> Optional[chat_model.Message]:
    db_message = await get_message(db, message_id)
    if not db_message:
        return None

    chat_id = db_message.chatId
    parent_id = db_message.parentId

    result = await db.execute(select(chat_model.Message).filter(chat_model.Message.chatId == chat_id))
    all_messages = result.scalars().all()

    parent_map = {}
    for msg in all_messages:
        parent_map.setdefault(msg.parentId, []).append(msg)

    def get_descendants(n_id):
        desc = []
        for child in parent_map.get(n_id, []):
            desc.append(child)
            desc.extend(get_descendants(child.id))
        return desc

    descendants = get_descendants(message_id)
    descendant_ids = [d.id for d in descendants]

    if parent_map.get(message_id):
        child_ids = [c.id for c in parent_map[message_id]]
        await db.execute(
            update(chat_model.Message)
            .where(chat_model.Message.id.in_(child_ids))
            .values(parentId=parent_id)
        )

    if descendant_ids:
        await db.execute(
            update(chat_model.Message)
            .where(chat_model.Message.id.in_(descendant_ids))
            .values(sortOrder=chat_model.Message.sortOrder - 1)
        )

    await db.delete(db_message)
    await db.commit()

    return db_message


async def delete_last_assistant_message(db: AsyncSession, chat_id: str) -> Optional[chat_model.Message]:
    active_list = await _get_active_linear_path(db, chat_id)
    for msg in reversed(active_list):
        if msg.role == schemas.MessageRole.ASSISTANT:
            return await delete_message(db, msg.id)
    return None


async def activate_message_path(db: AsyncSession, message_id: str) -> bool:
    db_message = await get_message(db, message_id)
    if not db_message:
        return False

    chat_id = db_message.chatId
    result = await db.execute(select(chat_model.Message).filter(chat_model.Message.chatId == chat_id))
    all_messages = result.scalars().all()

    node_map = {msg.id: msg for msg in all_messages}
    parent_map = {}
    for msg in all_messages:
        parent_map.setdefault(msg.parentId, []).append(msg)

    now = get_configured_now()
    to_update_ids = set()

    # 1. 向上回溯：收集所有祖先节点
    curr = db_message
    while curr:
        to_update_ids.add(curr.id)
        curr = node_map.get(curr.parentId)

    # 2. 向下延伸：找到当前激活的叶子节点（如果存在且连续）
    curr = db_message
    while True:
        children = parent_map.get(curr.id, [])
        if not children:
            break

        max_child = max(children, key=lambda x: _safe_timestamp(x.lastActiveAt))

        curr_time = _safe_timestamp(curr.lastActiveAt)
        child_time = _safe_timestamp(max_child.lastActiveAt)
        if curr_time - child_time > 0.1:
            break

        curr = max_child
        to_update_ids.add(curr.id)

    # 3. 更新整条路径的时间戳为 now
    if to_update_ids:
        await db.execute(
            update(chat_model.Message)
            .where(chat_model.Message.id.in_(to_update_ids))
            .values(lastActiveAt=now)
        )
        await db.commit()

    return True


async def create_sub_message(
        db: AsyncSession,
        message_id: str,
        sub_message_data: schemas.SubMessageCreate,
        sub_message_id: Optional[str] = None
) -> chat_model.SubMessage:
    final_id = sub_message_id or sub_message_data.id or chat_model.generate_uuid()
    db_sub_message = chat_model.SubMessage(
        id=final_id,
        messageId=message_id,
        content=sub_message_data.content,
        sortOrder=sub_message_data.sortOrder,
        type=sub_message_data.type,
        status=sub_message_data.status.value,
        config=sub_message_data.config.model_dump_json()
    )
    db.add(db_sub_message)
    await db.commit()
    await db.refresh(db_sub_message)
    return db_sub_message


async def get_sub_message(db: AsyncSession, sub_message_id: str) -> Optional[chat_model.SubMessage]:
    result = await db.execute(select(chat_model.SubMessage).filter(chat_model.SubMessage.id == sub_message_id))
    return result.scalars().first()


async def update_sub_message(db: AsyncSession, sub_message_id: str, sub_message_update: schemas.SubMessageUpdate) -> \
Optional[chat_model.SubMessage]:
    db_sub_message = await get_sub_message(db, sub_message_id)
    if not db_sub_message:
        return None

    update_data = sub_message_update.model_dump(exclude_unset=True)
    if 'content' in update_data:
        db_sub_message.content = update_data['content']
    if 'config' in update_data:
        db_sub_message.config = json.dumps(update_data['config'])
    if 'status' in update_data and update_data['status'] is not None:
        db_sub_message.status = update_data['status'].value

    await db.commit()
    await db.refresh(db_sub_message)
    return db_sub_message


async def update_sub_message_status(db: AsyncSession, sub_message_id: str, status: schemas.MessageStatus):
    stmt = update(chat_model.SubMessage).where(chat_model.SubMessage.id == sub_message_id).values(status=status.value)
    await db.execute(stmt)
    await db.commit()


async def append_to_sub_message_content(db: AsyncSession, sub_message_id: str, chunk: str):
    stmt = (
        update(chat_model.SubMessage)
        .where(chat_model.SubMessage.id == sub_message_id)
        .values(content=chat_model.SubMessage.content + chunk)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)
    await db.commit()
