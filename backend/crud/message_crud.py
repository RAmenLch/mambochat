# backend/crud/message_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, update
from typing import List, Optional
import json

from backend.models import chat_model
from backend import schemas

async def get_message(db: AsyncSession, message_id: str) -> Optional[chat_model.Message]:
    """通过ID获取单条消息（包含其所有子消息）"""
    result = await db.execute(
        select(chat_model.Message)
        .options(selectinload(chat_model.Message.sub_messages))
        .filter(chat_model.Message.id == message_id)
    )
    return result.scalars().first()


async def update_message(db: AsyncSession, message_id: str, message_update: schemas.MessageUpdate) -> Optional[chat_model.Message]:
    """通过替换其所有子消息来更新一条消息"""
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


async def get_messages_by_chat(db: AsyncSession, chat_id: str, skip: int = 0, limit: Optional[int] = None) -> List[chat_model.Message]:
    """获取指定会话的所有消息（包含子消息，按排序权重升序）"""
    query = (
        select(chat_model.Message)
        .options(selectinload(chat_model.Message.sub_messages))
        .filter(chat_model.Message.chatId == chat_id)
        .order_by(chat_model.Message.sortOrder.asc())
        .offset(skip)
    )

    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def get_limited_recent_messages(db: AsyncSession, chat_id: str, limit: int) -> List[chat_model.Message]:
    """获取指定会话中最新的N条消息（包含子消息，按时间升序返回）"""
    result = await db.execute(
        select(chat_model.Message)
        .options(selectinload(chat_model.Message.sub_messages))
        .filter(chat_model.Message.chatId == chat_id)
        .order_by(chat_model.Message.sortOrder.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return messages[::-1]


async def create_message(db: AsyncSession, message: schemas.MessageCreate, chat_id: str) -> chat_model.Message:
    """在指定会话中创建一条新消息及其关联的子消息"""
    max_sort_order_result = await db.execute(
        select(func.max(chat_model.Message.sortOrder)).filter(chat_model.Message.chatId == chat_id)
    )
    max_sort_order = max_sort_order_result.scalar_one_or_none()
    new_sort_order = (max_sort_order or 0) + 1

    db_message = chat_model.Message(
        role=message.role,
        chatId=chat_id,
        sortOrder=new_sort_order
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

    await db.commit()
    await db.refresh(db_message, ['sub_messages'])
    return db_message


async def delete_message(db: AsyncSession, message_id: str) -> Optional[chat_model.Message]:
    """通过ID删除单条消息"""
    db_message = await get_message(db, message_id)
    if db_message:
        await db.delete(db_message)
        await db.commit()
    return db_message


async def delete_messages_after(db: AsyncSession, chat_id: str, message_id: str, include_self: bool = False):
    """删除指定会话中某条消息之后的所有消息"""
    ref_message = await get_message(db, message_id=message_id)
    if not ref_message:
        return 0

    stmt = select(chat_model.Message).where(chat_model.Message.chatId == chat_id)
    if include_self:
        stmt = stmt.where(chat_model.Message.sortOrder >= ref_message.sortOrder)
    else:
        stmt = stmt.where(chat_model.Message.sortOrder > ref_message.sortOrder)

    result = await db.execute(stmt)
    messages_to_delete = result.scalars().all()

    if not messages_to_delete:
        return 0

    count = len(messages_to_delete)
    for msg in messages_to_delete:
        await db.delete(msg)

    await db.commit()
    return count


async def delete_last_assistant_message(db: AsyncSession, chat_id: str) -> Optional[chat_model.Message]:
    """删除指定会话中最新的一条 'assistant' 消息"""
    result = await db.execute(
        select(chat_model.Message)
        .filter(chat_model.Message.chatId == chat_id)
        .filter(chat_model.Message.role == schemas.MessageRole.ASSISTANT)
        .order_by(chat_model.Message.sortOrder.desc())
        .limit(1)
    )
    last_message = result.scalars().first()

    if last_message:
        await db.delete(last_message)
        await db.commit()

    return last_message


async def create_sub_message(
        db: AsyncSession,
        message_id: str,
        sub_message_data: schemas.SubMessageCreate,
        sub_message_id: Optional[str] = None  # 新增可选参数
) -> chat_model.SubMessage:
    """在指定消息下创建一个新的子消息。"""
    # 优先使用函数参数传入的 ID，其次使用 schema 中的 ID (如果有)，最后自动生成
    final_id = sub_message_id or sub_message_data.id or chat_model.generate_uuid()
    db_sub_message = chat_model.SubMessage(
        id=final_id,  # 显式赋值 ID
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
    """通过ID获取单条子消息"""
    result = await db.execute(select(chat_model.SubMessage).filter(chat_model.SubMessage.id == sub_message_id))
    return result.scalars().first()


async def update_sub_message(db: AsyncSession, sub_message_id: str, sub_message_update: schemas.SubMessageUpdate) -> Optional[chat_model.SubMessage]:
    """更新一条子消息的内容、配置或状态"""
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
    """高效地仅更新单个子消息的状态"""
    stmt = update(chat_model.SubMessage).where(chat_model.SubMessage.id == sub_message_id).values(status=status.value)
    await db.execute(stmt)
    await db.commit()


async def append_to_sub_message_content(db: AsyncSession, sub_message_id: str, chunk: str):
    """将文本块追加到现有子消息的内容中"""
    stmt = (
        update(chat_model.SubMessage)
        .where(chat_model.SubMessage.id == sub_message_id)
        .values(content=chat_model.SubMessage.content + chunk)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)
    await db.commit()

