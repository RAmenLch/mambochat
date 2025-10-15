# backend/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func, delete, update
from typing import List, Optional
import json

from . import models, schemas


# --- GlobalSettings CRUD ---

async def get_setting(db: AsyncSession, key: str) -> Optional[models.GlobalSettings]:
    """通过键获取单个全局配置项"""
    result = await db.execute(select(models.GlobalSettings).filter(models.GlobalSettings.key == key))
    return result.scalars().first()


async def update_setting(db: AsyncSession, setting: schemas.GlobalSetting) -> models.GlobalSettings:
    """更新或创建(upsert)一个全局配置项"""
    db_setting = await get_setting(db, setting.key)
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = models.GlobalSettings(**setting.model_dump())
        db.add(db_setting)
    await db.commit()
    await db.refresh(db_setting)
    return db_setting


# --- AIProvider CRUD ---

async def get_provider(db: AsyncSession, provider_id: str) -> Optional[models.AIProvider]:
    """通过ID获取单个AI服务提供商（包含其下的模型）"""
    result = await db.execute(
        select(models.AIProvider)
        .options(selectinload(models.AIProvider.models))
        .filter(models.AIProvider.id == provider_id)
    )
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


async def create_provider_with_models(db: AsyncSession,
                                      provider_data: schemas.ProviderWithModelsCreate) -> models.AIProvider:
    """事务性地创建一个服务商及其关联的模型"""
    provider_id = provider_data.id if provider_data.id else models.generate_uuid()

    db_provider = models.AIProvider(
        id=provider_id,
        name=provider_data.name,
        apiHost=provider_data.apiHost,
        apiKey=provider_data.apiKey
    )
    db.add(db_provider)

    for model_schema in provider_data.models:
        db_model = models.AIModel(
            id=models.generate_uuid(),
            modelId=model_schema.modelId,
            name=model_schema.name,
            providerId=provider_id
        )
        db.add(db_model)

    await db.commit()
    await db.refresh(db_provider, ['models'])

    return db_provider


async def update_provider(db: AsyncSession, provider_id: str, provider_update: schemas.AIProviderUpdate) -> Optional[models.AIProvider]:
    """更新一个AI服务提供商的信息"""
    db_provider = await get_provider(db, provider_id)
    if not db_provider:
        return None

    update_data = provider_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_provider, key, value)

    await db.commit()
    await db.refresh(db_provider)

    return db_provider


async def delete_provider(db: AsyncSession, provider_id: str) -> Optional[models.AIProvider]:
    """删除一个AI服务提供商及其下所有模型"""
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
    db_model = models.AIModel(
        id=models.generate_uuid(),
        **model.model_dump()
    )
    db.add(db_model)
    await db.commit()
    await db.refresh(db_model)
    return db_model


async def update_model(db: AsyncSession, model_id: str, model_update: schemas.AIModelUpdate) -> Optional[models.AIModel]:
    """更新一个AI模型的信息"""
    db_model = await get_model(db, model_id)
    if not db_model:
        return None

    update_data = model_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_model, key, value)

    await db.commit()
    await db.refresh(db_model)
    return db_model


async def delete_model(db: AsyncSession, model_id: str) -> Optional[models.AIModel]:
    """删除一个AI模型，并将使用此模型的所有会话的 aiModelId 置为 NULL"""
    db_model = await get_model(db, model_id)
    if db_model:
        await db.execute(
            update(models.Chat)
            .where(models.Chat.aiModelId == model_id)
            .values(aiModelId=None)
        )
        await db.delete(db_model)
        await db.commit()
    return db_model


# --- Chat CRUD ---

async def get_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
    """通过ID获取单个聊天会话（包含其所有消息、子消息、模型和提供商信息）"""
    result = await db.execute(
        select(models.Chat)
        .options(
            selectinload(models.Chat.messages).selectinload(models.Message.sub_messages),
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


async def duplicate_chat(db: AsyncSession, chat_id: str) -> Optional[models.Chat]:
    """复制一个现有会话及其所有消息和子消息来创建一个新会话"""
    original_chat = await get_chat(db, chat_id=chat_id)
    if not original_chat or original_chat.itemType != 'chat':
        return None

    max_sort_order_result = await db.execute(
        select(func.max(models.Chat.sortOrder))
        .filter(models.Chat.parentId == original_chat.parentId)
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
            new_msg = models.Message(
                role=msg.role,
                sortOrder=msg.sortOrder,
                chatId=new_chat.id
            )
            db.add(new_msg)
            # 必须先 flush 以获取 new_msg.id
            await db.flush()

            new_sub_messages = [
                models.SubMessage(
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


# --- Message & SubMessage CRUD ---

async def get_message(db: AsyncSession, message_id: str) -> Optional[models.Message]:
    """通过ID获取单条消息（包含其所有子消息）"""
    result = await db.execute(
        select(models.Message)
        .options(selectinload(models.Message.sub_messages))
        .filter(models.Message.id == message_id)
    )
    return result.scalars().first()


async def update_message(db: AsyncSession, message_id: str, message_update: schemas.MessageUpdate) -> Optional[models.Message]:
    """通过替换其所有子消息来更新一条消息"""
    db_message = await get_message(db, message_id=message_id)
    if not db_message:
        return None

    # 删除所有旧的子消息
    for sub_message in db_message.sub_messages:
        await db.delete(sub_message)
    await db.flush()

    # 创建新的子消息
    new_sub_messages = []
    for sub_msg_data in message_update.sub_messages:
        new_sub_msg = models.SubMessage(
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


async def get_messages_by_chat(db: AsyncSession, chat_id: str, skip: int = 0, limit: Optional[int] = None) -> List[models.Message]:
    """获取指定会话的所有消息（包含子消息，按排序权重升序）"""
    query = (
        select(models.Message)
        .options(selectinload(models.Message.sub_messages))
        .filter(models.Message.chatId == chat_id)
        .order_by(models.Message.sortOrder.asc())
        .offset(skip)
    )

    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def get_limited_recent_messages(db: AsyncSession, chat_id: str, limit: int) -> List[models.Message]:
    """获取指定会话中最新的N条消息（包含子消息，按时间升序返回）"""
    result = await db.execute(
        select(models.Message)
        .options(selectinload(models.Message.sub_messages))
        .filter(models.Message.chatId == chat_id)
        .order_by(models.Message.sortOrder.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return messages[::-1]


async def create_message(db: AsyncSession, message: schemas.MessageCreate, chat_id: str) -> models.Message:
    """在指定会话中创建一条新消息及其关联的子消息"""
    max_sort_order_result = await db.execute(
        select(func.max(models.Message.sortOrder)).filter(models.Message.chatId == chat_id)
    )
    max_sort_order = max_sort_order_result.scalar_one_or_none()
    new_sort_order = (max_sort_order or 0) + 1

    db_message = models.Message(
        role=message.role,
        chatId=chat_id,
        sortOrder=new_sort_order
    )
    db.add(db_message)
    await db.flush()  # Flush to get the db_message.id for foreign key reference

    for sub_msg_data in message.sub_messages:
        db_sub_message = models.SubMessage(
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


async def delete_message(db: AsyncSession, message_id: str) -> Optional[models.Message]:
    """通过ID删除单条消息（其子消息会因cascade被一并删除）"""
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

    # 构建查询以选择要删除的消息对象
    stmt = select(models.Message).where(models.Message.chatId == chat_id)
    if include_self:
        stmt = stmt.where(models.Message.sortOrder >= ref_message.sortOrder)
    else:
        stmt = stmt.where(models.Message.sortOrder > ref_message.sortOrder)

    result = await db.execute(stmt)
    messages_to_delete = result.scalars().all()

    if not messages_to_delete:
        return 0

    count = len(messages_to_delete)
    # 通过ORM会话删除对象，以触发级联删除
    for msg in messages_to_delete:
        await db.delete(msg)

    await db.commit()
    return count


async def delete_last_assistant_message(db: AsyncSession, chat_id: str) -> Optional[models.Message]:
    """删除指定会话中最新的一条 'assistant' 消息"""
    result = await db.execute(
        select(models.Message)
        .filter(models.Message.chatId == chat_id)
        .filter(models.Message.role == schemas.MessageRole.ASSISTANT)
        .order_by(models.Message.sortOrder.desc())
        .limit(1)
    )
    last_message = result.scalars().first()

    if last_message:
        await db.delete(last_message)
        await db.commit()

    return last_message


async def get_sub_message(db: AsyncSession, sub_message_id: str) -> Optional[models.SubMessage]:
    """通过ID获取单条子消息"""
    result = await db.execute(select(models.SubMessage).filter(models.SubMessage.id == sub_message_id))
    return result.scalars().first()


async def update_sub_message(db: AsyncSession, sub_message_id: str, sub_message_update: schemas.SubMessageUpdate) -> Optional[models.SubMessage]:
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
    stmt = update(models.SubMessage).where(models.SubMessage.id == sub_message_id).values(status=status.value)
    await db.execute(stmt)
    await db.commit()


async def append_to_sub_message_content(db: AsyncSession, sub_message_id: str, chunk: str):
    """将文本块追加到现有子消息的内容中"""
    stmt = (
        update(models.SubMessage)
        .where(models.SubMessage.id == sub_message_id)
        .values(content=models.SubMessage.content + chunk)
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)
    await db.commit()
