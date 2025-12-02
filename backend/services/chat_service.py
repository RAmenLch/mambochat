# backend/services/chat_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional
import json

from backend.crud import chat_crud
from backend import schemas
from backend.models import chat_model

async def duplicate_chat_with_messages(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """
    复制一个现有会话及其所有消息和子消息来创建一个新会话。
    这是一个包含业务逻辑的服务层函数。
    """
    original_chat = await chat_crud.get_chat(db, chat_id=chat_id)
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
    new_chat = await chat_crud.create_chat(db, chat=new_chat_data)

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

