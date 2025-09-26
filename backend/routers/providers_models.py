# backend/routers/providers_models.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from .. import crud, schemas
from ..database import get_db

router = APIRouter()

# --- AIProvider Routes ---

@router.post(
    "/providers/",
    response_model=schemas.AIProvider,
    status_code=status.HTTP_201_CREATED,
    summary="创建AI服务商"
)
async def create_provider(provider: schemas.AIProviderCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的AI服务提供商。
    - **id**: (可选) 自定义ID，如 'openai'。若不提供，则自动生成UUID。
    - **name**: 服务商名称, e.g., "OpenAI"。
    - **apiHost**: API基础地址, e.g., "https://api.openai.com/v1"。
    - **apiKey**: 访问API所需的密钥。
    """
    # 可以在这里添加逻辑，检查 provider.id 是否已存在
    return await crud.create_provider(db=db, provider=provider)


@router.get(
    "/providers/",
    response_model=List[schemas.AIProviderWithModels],
    summary="获取所有AI服务商及其模型"
)
async def read_providers(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    获取所有AI服务提供商的列表，并同时加载他们拥有的所有模型。
    """
    providers = await crud.get_providers(db, skip=skip, limit=limit)
    return providers

@router.delete("/providers/{provider_id}", response_model=schemas.AIProvider, summary="删除AI服务商")
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    通过ID删除一个AI服务提供商。
    注意：其下关联的所有AI模型也会被一并删除。
    """
    db_provider = await crud.delete_provider(db, provider_id=provider_id)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return db_provider




# --- AIModel Routes ---

@router.post(
    "/models/",
    response_model=schemas.AIModel,
    status_code=status.HTTP_201_CREATED,
    summary="为服务商添加新模型"
)
async def create_model(model: schemas.AIModelCreate, db: AsyncSession = Depends(get_db)):
    """
    为一个已存在的服务商添加一个新的AI模型配置。
    - **modelId**: 模型在API中使用的ID, e.g., "gpt-4o"。
    - **name**: 模型的显示名称, e.g., "GPT-4o"。
    - **providerId**: 该模型所属的服务商ID。
    """
    # 验证 providerId 是否存在
    db_provider = await crud.get_provider(db, provider_id=model.providerId)
    if not db_provider:
        raise HTTPException(status_code=404, detail=f"Provider with id {model.providerId} not found")
    return await crud.create_model(db=db, model=model)


@router.delete("/models/{model_id}", response_model=schemas.AIModel, summary="删除AI模型")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """
    通过ID删除一个AI模型配置。
    """
    db_model = await crud.delete_model(db, model_id=model_id)
    if db_model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return db_model