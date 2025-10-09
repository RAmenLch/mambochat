# backend/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func
from typing import List, Optional
import json

from . import models, schemas


# --- AIProvider CRUD ---

async def get_provider(db: AsyncSession, provider_id: str) -> Optional[models.AIProvider]:
    """通过ID获取单个AI服务提供商"""
    result = await db.execute(select(models.AIProvider).filter(models.AIProvider.id == provider_id))
    return result.scalars().first()


async def get_providers(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.AIProvider]:
    """获取AI服务提供商列表（包含其下的模型）"""
    result = await db.execute(
        select(models.AIProvider)
        .options(selectinload(models.AIProvider.models))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_provider(db: AsyncSession, provider: schemas.AIProviderCreate) -> models.AIProvider:
    """创建一个新的AI服务提供商"""
    provider_id = provider.id if provider.id else models.generate_uuid()
    db_provider = models.AIProvider(
        id=provider_id,
        name=provider.name,
        apiHost=provider.apiHost,
        apiKey=provider.apiKey
    )
    db.add(db_provider)
    await db.commit()
    await db.refresh(db_provider)
    return db_provider


async def delete_provider(db: AsyncSession, provider_id: str) -> Optional[models.AIProvider]:
    """删除一个AI服务提供商及其下所有模型 (利用cascade)"""
    db_provider = await get_provider(db, provider_id)
    if db_provider:
        await db.delete(db_provider)
        await db.commit()
    return db_provider


# --- AIModel CRUD ---

async def get_model(db: AsyncSession, model_id: str) -> Optional[models.AIModel]:
    """通过ID获取单个AI模型"""
    result = await db.execute(select(models.AIModel).filter(models.AIModel.id == model_id))
    return result.scalars().first()


async def get_models_by_provider(db: AsyncSession, provider_id: str) -> List[models.AIModel]:
    """获取指定提供商下的所有模型"""
    result = await db.execute(select(models.AIModel).filter(models.AIModel.providerId == provider_id))
    return result.scalars().all()


async def create_model(db: AsyncSession, model: schemas.AIModelCreate) -> models.AIModel:
    """为提供商创建一个新的AI模型"""
    db_model = models.AIModel(**model.model_dump())
    db.add(db_model)
    await db.commit()
    await db.refresh(db_model)
    return db_model


async def delete_model(db: AsyncSession, model_id: str) -> Optional[models.AIModel]:
    """删除一个AI模型"""
    db_model = await get_model(db, model_id)
    if db_model:
        await db.delete(db_model)
        await db.commit()
    return db_model


# --- Chat CRUD ---

async def get_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
    """通过ID获取单个聊天会话（包含其所有消息、模型和提供商信息）"""
    result = await db.execute(
        select(models.Chat)
        .options(
            selectinload(models.Chat.messages),
            joinedload(models.Chat.ai_model).joinedload(models.AIModel.provider)
        )
        .filter(models.Chat.id == chat_id)
    )
    return result.scalars().first()


async def get_chats(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.Chat]:
    """获取会话和文件夹列表（按排序权重升序）"""
    result = await db.execute(
        select(models.Chat)
        .order_by(models.Chat.sortOrder.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_chat(db: AsyncSession, chat: schemas.ChatCreate) -> models.Chat:
    """创建一个新的聊天会话或文件夹"""
    chat_data = chat.model_dump()
    if chat_data.get("modelParameters") is not None:
        chat_data["modelParameters"] = json.dumps(chat_data["modelParameters"])

    db_chat = models.Chat(**chat_data)
    db.add(db_chat)
    await db.commit()
    await db.refresh(db_chat)
    return db_chat


async def update_chat(db: AsyncSession, chat_id: str, chat_update: schemas.ChatUpdate) -> Optional[models.Chat]:
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


async def delete_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
    """删除一个聊天会话或文件夹"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if db_chat:
        await db.delete(db_chat)
        await db.commit()
    return db_chat


async def touch_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
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
    result = await db.execute(select(models.Chat).filter(models.Chat.id.in_(chat_ids)))
    chats_map = {chat.id: chat for chat in result.scalars().all()}

    for update_item in updates:
        chat_to_update = chats_map.get(update_item.id)
        if chat_to_update:
            chat_to_update.parentId = update_item.parentId
            chat_to_update.sortOrder = update_item.sortOrder

    await db.commit()
    return True


# --- Message CRUD ---

async def get_message(db: AsyncSession, message_id: str) -> Optional[models.Message]:
    """通过ID获取单条消息"""
    result = await db.execute(select(models.Message).filter(models.Message.id == message_id))
    return result.scalars().first()


async def update_message(db: AsyncSession, message_id: str, message_update: schemas.MessageUpdate) -> Optional[models.Message]:
    """更新一条已存在消息的内容"""
    db_message = await get_message(db, message_id=message_id)
    if not db_message:
        return None

    db_message.content = message_update.content
    await db.commit()
    await db.refresh(db_message)
    return db_message


async def get_messages_by_chat(db: AsyncSession, chat_id: str, skip: int = 0, limit: int = 1000) -> List[
    models.Message]:
    """获取指定会话的所有消息"""
    result = await db.execute(
        select(models.Message)
        .filter(models.Message.chatId == chat_id)
        .order_by(models.Message.createdAt.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_message(db: AsyncSession, message: schemas.MessageCreate, chat_id: str) -> models.Message:
    """在指定会话中创建一条新消息"""
    db_message = models.Message(
        **message.model_dump(),
        chatId=chat_id
    )
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message


async def delete_last_assistant_message(db: AsyncSession, chat_id: str) -> Optional[models.Message]:
    """删除指定会话中最新的一条 'assistant' 消息"""
    result = await db.execute(
        select(models.Message)
        .filter(models.Message.chatId == chat_id)
        .filter(models.Message.role == schemas.MessageRole.ASSISTANT)
        .order_by(models.Message.createdAt.desc())
        .limit(1)
    )
    last_message = result.scalars().first()

    if last_message:
        await db.delete(last_message)
        await db.commit()

    return last_message
