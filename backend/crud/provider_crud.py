# backend/crud/provider_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import update
from typing import List, Optional

from ..models import provider_model, chat_model
from ..models.base_model import generate_uuid
from .. import schemas

async def get_provider(db: AsyncSession, provider_id: str) -> Optional[provider_model.AIProvider]:
    """通过ID获取单个AI服务提供商（包含其下的模型）"""
    result = await db.execute(
        select(provider_model.AIProvider)
        .options(selectinload(provider_model.AIProvider.models))
        .filter(provider_model.AIProvider.id == provider_id)
    )
    return result.scalars().first()


async def get_providers(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[provider_model.AIProvider]:
    """获取AI服务提供商列表（包含其下的模型）"""
    result = await db.execute(
        select(provider_model.AIProvider)
        .options(selectinload(provider_model.AIProvider.models))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_provider_with_models(db: AsyncSession,
                                      provider_data: schemas.ProviderWithModelsCreate) -> provider_model.AIProvider:
    """事务性地创建一个服务商及其关联的模型"""
    provider_id = provider_data.id if provider_data.id else generate_uuid()

    # 从 Pydantic 模型中 dump 数据时，排除 'models' 和 'id'
    # 'models' 需要单独处理，'id' 我们已经手动生成并会显式传递
    provider_create_data = provider_data.model_dump(exclude={'models', 'id'})
    db_provider = provider_model.AIProvider(id=provider_id, **provider_create_data)
    db.add(db_provider)

    for model_schema in provider_data.models:
        db_model = provider_model.AIModel(
            id=generate_uuid(),
            **model_schema.model_dump(),  # 传递所有模型数据，包括 meta_config
            providerId=provider_id
        )
        db.add(db_model)

    await db.commit()
    await db.refresh(db_provider, ['models'])

    return db_provider


async def update_provider(db: AsyncSession, provider_id: str, provider_update: schemas.AIProviderUpdate) -> Optional[provider_model.AIProvider]:
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


async def delete_provider(db: AsyncSession, provider_id: str) -> Optional[provider_model.AIProvider]:
    """删除一个AI服务提供商及其下所有模型"""
    db_provider = await get_provider(db, provider_id)
    if db_provider:
        await db.delete(db_provider)
        await db.commit()
    return db_provider


async def get_model(db: AsyncSession, model_id: str) -> Optional[provider_model.AIModel]:
    """通过ID获取单个AI模型（并预加载其提供商信息）"""
    result = await db.execute(
        select(provider_model.AIModel)
        .options(joinedload(provider_model.AIModel.provider))
        .filter(provider_model.AIModel.id == model_id)
    )
    return result.scalars().first()


async def get_models_by_provider(db: AsyncSession, provider_id: str) -> List[provider_model.AIModel]:
    """获取指定提供商下的所有模型"""
    result = await db.execute(select(provider_model.AIModel).filter(provider_model.AIModel.providerId == provider_id))
    return result.scalars().all()


async def create_model(db: AsyncSession, model: schemas.AIModelCreate) -> provider_model.AIModel:
    """为提供商创建一个新的AI模型"""
    db_model = provider_model.AIModel(
        id=generate_uuid(),
        **model.model_dump()
    )
    db.add(db_model)
    await db.commit()
    await db.refresh(db_model)
    return db_model


async def update_model(db: AsyncSession, model_id: str, model_update: schemas.AIModelUpdate) -> Optional[provider_model.AIModel]:
    """更新一个AI模型的信息"""
    db_model = await get_model(db, model_id)
    if not db_model:
        return None

    update_data = model_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        # 如果更新的是 meta_config，需要特殊处理字典的合并
        if key == 'meta_config' and value is not None and db_model.meta_config is not None:
            # 将传入的更新与现有的配置合并
            merged_config = db_model.meta_config.copy()
            merged_config.update(value)
            setattr(db_model, key, merged_config)
        else:
            setattr(db_model, key, value)

    await db.commit()
    await db.refresh(db_model)
    return db_model


async def delete_model(db: AsyncSession, model_id: str) -> Optional[provider_model.AIModel]:
    """删除一个AI模型，并将使用此模型的所有会话的 aiModelId 置为 NULL"""
    db_model = await get_model(db, model_id)
    if db_model:
        await db.execute(
            update(chat_model.Chat)
            .where(chat_model.Chat.aiModelId == model_id)
            .values(aiModelId=None)
        )
        await db.delete(db_model)
        await db.commit()
    return db_model
