# backend/crud/chat_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func
from typing import List, Optional
import json

from ..models import chat_model
from .. import schemas

async def get_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """通过ID获取单个聊天会话（包含其所有消息、子消息、模型和提供商信息）"""
    result = await db.execute(
        select(chat_model.Chat)
        .options(
            selectinload(chat_model.Chat.messages).selectinload(chat_model.Message.sub_messages),
            joinedload(chat_model.Chat.ai_model).joinedload(chat_model.AIModel.provider)
        )
        .filter(chat_model.Chat.id == chat_id)
    )
    return result.scalars().first()


async def get_chats(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[chat_model.Chat]:
    """获取会话和文件夹列表（按排序权重升序）"""
    result = await db.execute(
        select(chat_model.Chat)
        .order_by(chat_model.Chat.sortOrder.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_chat(db: AsyncSession, chat: schemas.ChatCreate) -> chat_model.Chat:
    """创建一个新的聊天会话或文件夹"""
    chat_data = chat.model_dump()
    if chat_data.get("modelParameters") is not None:
        chat_data["modelParameters"] = json.dumps(chat_data["modelParameters"])

    db_chat = chat_model.Chat(**chat_data)
    db.add(db_chat)
    await db.commit()
    await db.refresh(db_chat)
    return db_chat


async def update_chat(db: AsyncSession, chat_id: str, chat_update: schemas.ChatUpdate) -> Optional[chat_model.Chat]:
    """更新会话或文件夹的配置信息"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if not db_chat:
        return None

    update_data = chat_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if key == "modelParameters" and value is not None:
            setattr(db_chat, key, json.dumps(value))
        else:
            setattr(db_chat, key, value)

    await db.commit()
    await db.refresh(db_chat)
    return db_chat


async def delete_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """删除一个聊天会话或文件夹"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if db_chat:
        await db.delete(db_chat)
        await db.commit()
    return db_chat


async def touch_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """更新会话的 lastOpenedAt 时间戳"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if db_chat:
        db_chat.lastOpenedAt = func.now()
        await db.commit()
        await db.refresh(db_chat)
    return db_chat


async def batch_update_chats_order(db: AsyncSession, updates: List[schemas.ChatReorderItem]) -> bool:
    """批量更新会话和文件夹的顺序与层级"""
    if not updates:
        return True

    chat_ids = [item.id for item in updates]
    result = await db.execute(select(chat_model.Chat).filter(chat_model.Chat.id.in_(chat_ids)))
    chats_map = {chat.id: chat for chat in result.scalars().all()}

    for update_item in updates:
        chat_to_update = chats_map.get(update_item.id)
        if chat_to_update:
            chat_to_update.parentId = update_item.parentId
            chat_to_update.sortOrder = update_item.sortOrder

    await db.commit()
    return True


async def duplicate_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """复制一个现有会话及其所有消息和子消息来创建一个新会话"""
    original_chat = await get_chat(db, chat_id=chat_id)
    if not original_chat or original_chat.itemType != 'chat':
        return None

    max_sort_order_result = await db.execute(
        select(func.max(chat_model.Chat.sortOrder))
        .filter(chat_model.Chat.parentId == original_chat.parentId)
    )
    max_sort_order = max_sort_order_result.scalar_one_or_none()
    new_sort_order = (max_sort_order or 0) + 1

    try:
        params = json.loads(original_chat.modelParameters) if original_chat.modelParameters else None
    except json.JSONDecodeError:
        params = None

    new_chat_data = schemas.ChatCreate(
        name=f"{original_chat.name} (副本)",
        systemPrompt=original_chat.systemPrompt,
        modelParameters=params,
        aiModelId=original_chat.aiModelId,
        itemType='chat',
        parentId=original_chat.parentId,
        sortOrder=new_sort_order
    )
    new_chat = await create_chat(db, chat=new_chat_data)

    if original_chat.messages:
        for msg in original_chat.messages:
            new_msg = chat_model.Message(
                role=msg.role,
                sortOrder=msg.sortOrder,
                chatId=new_chat.id
            )
            db.add(new_msg)
            await db.flush()

            new_sub_messages = [
                chat_model.SubMessage(
                    content=sub.content,
                    sortOrder=sub.sortOrder,
                    type=sub.type,
                    config=sub.config,
                    status=sub.status,
                    messageId=new_msg.id
                )
                for sub in msg.sub_messages
            ]
            db.add_all(new_sub_messages)

        await db.commit()
        await db.refresh(new_chat, ['messages'])

    return new_chat

