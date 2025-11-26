# backend/routers/provider_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..crud import provider_crud, setting_crud
from .. import schemas
from ..database import get_db
from ..config.llm_parameters import SUPPORTED_LLM_PARAMETERS

router = APIRouter()

# --- Provider Management Routes ---

@router.post(
    "/providers/",
    response_model=schemas.AIProviderWithModels,
    status_code=status.HTTP_201_CREATED,
    summary="创建服务商及其模型"
)
async def create_provider(provider: schemas.ProviderWithModelsCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的服务商，并可选择性地同时创建其下的模型。
    创建成功后，会自动将该服务商设置为“最后选择的服务商”。
    """
    new_provider = await provider_crud.create_provider_with_models(db=db, provider_data=provider)

    await setting_crud.update_setting(
        db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=new_provider.id)
    )

    return new_provider


@router.get("/providers/", response_model=List[schemas.AIProviderWithModels], summary="获取服务商列表")
async def read_providers(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    获取所有AI服务商及其关联的模型列表。
    """
    return await provider_crud.get_providers(db, skip=skip, limit=limit)


@router.get("/providers/{provider_id}", response_model=schemas.AIProviderWithModels, summary="获取单个服务商")
async def read_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取指定ID的服务商及其所有模型。
    """
    db_provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return db_provider


@router.put("/providers/{provider_id}", response_model=schemas.AIProvider, summary="更新服务商")
async def update_provider(
    provider_id: str,
    provider_update: schemas.AIProviderUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    更新一个已存在的服务商信息。
    更新成功后，会自动将该服务商设置为“最后选择的服务商”。
    """
    updated_provider = await provider_crud.update_provider(db, provider_id=provider_id, provider_update=provider_update)
    if updated_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    await setting_crud.update_setting(
        db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=provider_id)
    )

    return updated_provider


@router.delete("/providers/{provider_id}", response_model=schemas.AIProvider, summary="删除服务商")
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除一个服务商及其下的所有模型。
    如果被删除的服务商或其模型与全局配置关联，则会一并清理这些配置。
    """
    db_provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    default_model_setting = await setting_crud.get_setting(db, "default_model_id")
    if default_model_setting and default_model_setting.value:
        provider_model_ids = {model.id for model in db_provider.models}
        if default_model_setting.value in provider_model_ids:
            await setting_crud.update_setting(db, setting=schemas.GlobalSetting(key="default_model_id", value=None))

    last_selected_setting = await setting_crud.get_setting(db, "last_selected_provider_id")
    if last_selected_setting and last_selected_setting.value == provider_id:
        await setting_crud.update_setting(db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=None))

    await provider_crud.delete_provider(db, provider_id=provider_id)
    return db_provider


# --- Model Management Routes ---

@router.post(
    "/models/",
    response_model=schemas.AIModel,
    status_code=status.HTTP_201_CREATED,
    summary="创建模型"
)
async def create_model(model: schemas.AIModelCreate, db: AsyncSession = Depends(get_db)):
    """
    为一个已存在的服务商添加一个新的模型。
    """
    provider = await provider_crud.get_provider(db, provider_id=model.providerId)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with id {model.providerId} not found"
        )
    return await provider_crud.create_model(db=db, model=model)


@router.put("/models/{model_id}", response_model=schemas.AIModel, summary="更新模型")
async def update_model(
    model_id: str,
    model_update: schemas.AIModelUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    更新一个已存在模型的信息（例如，显示名称或元配置）。
    """
    # 在更新前，校验 supported_parameters 是否合法
    if model_update.meta_config and model_update.meta_config.supported_parameters is not None:
        valid_parameter_keys = {param.key for param in SUPPORTED_LLM_PARAMETERS}
        invalid_keys = [
            key for key in model_update.meta_config.supported_parameters if key not in valid_parameter_keys
        ]
        if invalid_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid supported parameters found: {', '.join(invalid_keys)}. Please use keys available in the system configuration."
            )

    updated_model = await provider_crud.update_model(db, model_id=model_id, model_update=model_update)
    if updated_model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return updated_model


@router.delete("/models/{model_id}", response_model=schemas.AIModel, summary="删除模型")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除一个模型。
    如果该模型是全局默认模型，则会清空该配置。
    """
    default_model_setting = await setting_crud.get_setting(db, "default_model_id")
    if default_model_setting and default_model_setting.value == model_id:
        await setting_crud.update_setting(db, setting=schemas.GlobalSetting(key="default_model_id", value=None))

    db_model = await provider_crud.delete_model(db, model_id=model_id)
    if db_model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return db_model

