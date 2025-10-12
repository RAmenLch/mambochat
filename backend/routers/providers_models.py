# backend/routers/providers_models.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import httpx
import json

from ..services import llm_service
from .. import crud, schemas
from ..database import get_db

router = APIRouter()


# --- Provider Routes ---

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
    new_provider = await crud.create_provider_with_models(db=db, provider_data=provider)

    # 业务逻辑: 更新最后选择的服务商ID
    await crud.update_setting(
        db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=new_provider.id)
    )

    return new_provider


@router.get("/providers/", response_model=List[schemas.AIProviderWithModels], summary="获取服务商列表")
async def read_providers(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    获取所有AI服务商及其关联的模型列表。
    """
    return await crud.get_providers(db, skip=skip, limit=limit)


@router.get("/providers/{provider_id}", response_model=schemas.AIProviderWithModels, summary="获取单个服务商")
async def read_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取指定ID的服务商及其所有模型。
    """
    db_provider = await crud.get_provider(db, provider_id=provider_id)
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
    updated_provider = await crud.update_provider(db, provider_id=provider_id, provider_update=provider_update)
    if updated_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 业务逻辑: 更新最后选择的服务商ID
    await crud.update_setting(
        db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=provider_id)
    )

    return updated_provider


@router.delete("/providers/{provider_id}", response_model=schemas.AIProvider, summary="删除服务商")
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除一个服务商及其下的所有模型。
    如果被删除的服务商或其模型与全局配置关联，则会一并清理这些配置。
    """
    # 在删除前，先获取服务商信息以执行业务逻辑
    db_provider = await crud.get_provider(db, provider_id=provider_id)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 业务逻辑: 清理相关的全局设置
    default_model_setting = await crud.get_setting(db, "default_model_id")
    if default_model_setting and default_model_setting.value:
        provider_model_ids = {model.id for model in db_provider.models}
        if default_model_setting.value in provider_model_ids:
            await crud.update_setting(db, setting=schemas.GlobalSetting(key="default_model_id", value=None))

    last_selected_setting = await crud.get_setting(db, "last_selected_provider_id")
    if last_selected_setting and last_selected_setting.value == provider_id:
        await crud.update_setting(db, setting=schemas.GlobalSetting(key="last_selected_provider_id", value=None))

    # 执行数据库删除操作
    await crud.delete_provider(db, provider_id=provider_id)
    return db_provider


# --- Provider-related Services ---

@router.post("/providers/test-connection", response_model=schemas.ConnectionTestResponse, summary="测试连接")
async def test_connection(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，测试与外部 LLM 服务的连通性。
    """
    return await llm_service.test_connection_to_provider(api_host=request.apiHost, api_key=request.apiKey)


@router.post("/providers/fetch-models", response_model=List[schemas.AIModelBase], summary="获取外部模型列表")
async def fetch_models(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，从外部 LLM 服务获取可用的模型列表。
    """
    try:
        return await llm_service.fetch_models_from_provider(api_host=request.apiHost, api_key=request.apiKey)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="获取模型失败: 服务器返回的不是有效的JSON格式。请检查 API Host 是否正确。"
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        detail = f"获取模型失败: 服务器返回错误码 {status_code}。"
        if status_code == 401:
            detail += " API Key 无效或权限不足。"
        elif status_code == 404:
            detail += " 找不到模型接口，请检查 API Host。"
        raise HTTPException(status_code=status_code, detail=detail)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"获取模型失败: 无法连接到 API Host。({type(e).__name__})"
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取模型失败: 发生未知错误。")


@router.get("/providers/{provider_id}/fetch-models", response_model=List[schemas.AIModelBase], summary="为现有服务商获取模型")
async def fetch_models_for_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    使用已存储的凭证，为指定的服务商获取可用的模型列表。
    """
    provider = await crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    try:
        return await llm_service.fetch_models_from_provider(api_host=provider.apiHost, api_key=provider.apiKey)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="获取模型失败: 服务器返回的不是有效的JSON格式。请检查保存的 API Host 是否正确。"
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        detail = f"获取模型失败: 服务器返回错误码 {status_code}。"
        if status_code == 401:
            detail += " 保存的 API Key 无效或权限不足。"
        elif status_code == 404:
            detail += " 找不到模型接口，请检查保存的 API Host。"
        raise HTTPException(status_code=status_code, detail=detail)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"获取模型失败: 无法连接到 API Host。({type(e).__name__})"
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取模型失败: 发生未知错误。")


# --- Model Routes ---

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
    provider = await crud.get_provider(db, provider_id=model.providerId)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with id {model.providerId} not found"
        )
    return await crud.create_model(db=db, model=model)


@router.put("/models/{model_id}", response_model=schemas.AIModel, summary="更新模型")
async def update_model(
    model_id: str,
    model_update: schemas.AIModelUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    更新一个已存在模型的信息（例如，显示名称）。
    """
    updated_model = await crud.update_model(db, model_id=model_id, model_update=model_update)
    if updated_model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return updated_model


@router.delete("/models/{model_id}", response_model=schemas.AIModel, summary="删除模型")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除一个模型。
    如果该模型是全局默认模型，则会清空该配置。
    """
    # 业务逻辑: 检查该模型是否为全局默认模型
    default_model_setting = await crud.get_setting(db, "default_model_id")
    if default_model_setting and default_model_setting.value == model_id:
        await crud.update_setting(db, setting=schemas.GlobalSetting(key="default_model_id", value=None))

    # 执行数据库删除操作
    db_model = await crud.delete_model(db, model_id=model_id)
    if db_model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return db_model
