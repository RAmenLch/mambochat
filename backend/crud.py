# backend/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

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
        .options(selectinload(models.AIProvider.models)) # 预加载关联的 models
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def create_provider(db: AsyncSession, provider: schemas.AIProviderCreate) -> models.AIProvider:
    """创建一个新的AI服务提供商"""
    # 如果用户没有提供id，则自动生成
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
            selectinload(models.Chat.messages),  # 使用 selectinload 加载消息列表 (一对多)
            joinedload(models.Chat.ai_model).joinedload(models.AIModel.provider) # <--- 新增此行
        )
        .filter(models.Chat.id == chat_id)
    )
    return result.scalars().first()

async def get_chats(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.Chat]:
    """获取聊天会话列表（按创建时间降序）"""
    result = await db.execute(
        select(models.Chat)
        .order_by(models.Chat.createdAt.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def create_chat(db: AsyncSession, chat: schemas.ChatCreate) -> models.Chat:
    """创建一个新的聊天会话"""
    db_chat = models.Chat(**chat.model_dump())
    db.add(db_chat)
    await db.commit()
    await db.refresh(db_chat)
    return db_chat

async def delete_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
    """删除一个聊天会话"""
    db_chat = await get_chat(db, chat_id)
    if db_chat:
        await db.delete(db_chat)
        await db.commit()
    return db_chat


# --- Message CRUD ---

async def get_messages_by_chat(db: AsyncSession, chat_id: str, skip: int = 0, limit: int = 1000) -> List[models.Message]:
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

