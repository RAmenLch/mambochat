# backend/routers/providers_models.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import httpx

from .. import crud, schemas
from ..services import llm_service
from ..database import get_db

router = APIRouter()


# --- AIProvider Routes ---

@router.post(
    "/providers/",
    response_model=schemas.AIProviderWithModels,
    status_code=status.HTTP_201_CREATED,
    summary="创建AI服务商（可同时创建模型）"
)
async def create_provider_with_models(provider: schemas.ProviderWithModelsCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的AI服务提供商，并可选择性地一次性创建其下的多个模型。
    """
    return await crud.create_provider_with_models(db=db, provider_data=provider)


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


@router.put(
    "/providers/{provider_id}",
    response_model=schemas.AIProvider,
    summary="更新AI服务商信息"
)
async def update_provider(
    provider_id: str,
    provider_update: schemas.AIProviderUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    通过ID更新一个AI服务提供商的名称、API Host或API Key。
    """
    db_provider = await crud.update_provider(db, provider_id=provider_id, provider_update=provider_update)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="服务商未找到")
    return db_provider


@router.delete("/providers/{provider_id}", response_model=schemas.AIProvider, summary="删除AI服务商")
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    通过ID删除一个AI服务提供商。其下关联的所有AI模型也会被一并删除。
    """
    db_provider = await crud.delete_provider(db, provider_id=provider_id)
    if db_provider is None:
        raise HTTPException(status_code=404, detail="服务商未找到")
    return db_provider


@router.post(
    "/providers/test-connection",
    response_model=schemas.ConnectionTestResponse,
    summary="测试与服务商的连接"
)
async def test_connection(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，尝试连接服务商并验证凭证是否有效。
    """
    try:
        await llm_service.fetch_models_from_provider(api_host=request.apiHost, api_key=request.apiKey)
        return schemas.ConnectionTestResponse(status="success", message="连接成功")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return schemas.ConnectionTestResponse(status="error", message="认证失败，请检查 API Key。")
        else:
            return schemas.ConnectionTestResponse(status="error", message=f"连接失败，HTTP状态码: {e.response.status_code}")
    except httpx.RequestError as e:
        return schemas.ConnectionTestResponse(status="error", message=f"连接失败: {e}")
    except Exception as e:
        return schemas.ConnectionTestResponse(status="error", message=f"发生未知错误: {e}")


@router.post(
    "/providers/fetch-models",
    response_model=List[schemas.AIModelBase],
    summary="从服务商API获取模型列表"
)
async def fetch_external_models(request: schemas.ConnectionRequest):
    """
    从指定的 API Host 获取可用的模型列表，供用户选择添加。
    """
    try:
        models = await llm_service.fetch_models_from_provider(api_host=request.apiHost, api_key=request.apiKey)
        return models
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="认证失败，请检查 API Key。")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"获取模型列表失败: HTTP {e.response.status_code}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="无法连接到指定的服务商API Host。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表时发生未知错误: {e}")


@router.post(
    "/providers/{provider_id}/fetch-models",
    response_model=List[schemas.AIModelBase],
    summary="为已存在的服务商获取模型列表"
)
async def fetch_models_for_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    使用数据库中已存的凭证，为指定服务商获取模型列表。
    """
    db_provider = await crud.get_provider(db, provider_id=provider_id)
    if not db_provider:
        raise HTTPException(status_code=404, detail="服务商未找到")

    try:
        models = await llm_service.fetch_models_from_provider(api_host=db_provider.apiHost, api_key=db_provider.apiKey)
        return models
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="认证失败，请检查已保存的 API Key。")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"获取模型列表失败: HTTP {e.response.status_code}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="无法连接到该服务商的 API Host。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表时发生未知错误: {e}")


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
    """
    db_provider = await crud.get_provider(db, provider_id=model.providerId)
    if not db_provider:
        raise HTTPException(status_code=404, detail=f"服务商ID {model.providerId} 未找到")
    return await crud.create_model(db=db, model=model)


@router.put(
    "/models/{model_id}",
    response_model=schemas.AIModel,
    summary="更新AI模型信息"
)
async def update_model(
    model_id: str,
    model_update: schemas.AIModelUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    通过ID更新一个AI模型的显示名称。
    """
    db_model = await crud.update_model(db, model_id=model_id, model_update=model_update)
    if db_model is None:
        raise HTTPException(status_code=404, detail="模型未找到")
    return db_model


@router.delete("/models/{model_id}", response_model=schemas.AIModel, summary="删除AI模型")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """
    通过ID删除一个AI模型配置。
    如果该模型被设为全局默认模型，则禁止删除。
    """
    default_model_setting = await crud.get_setting(db, key="default_model_id")
    if default_model_setting and default_model_setting.value == model_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="无法删除，该模型已被设为全局默认模型。"
        )

    db_model = await crud.delete_model(db, model_id=model_id)
    if db_model is None:
        raise HTTPException(status_code=404, detail="模型未找到")
    return db_model
