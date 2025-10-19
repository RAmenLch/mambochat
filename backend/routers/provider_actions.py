# backend/routers/provider_actions.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import httpx
import json

from ..services import provider_service
from ..crud import provider_crud
from .. import schemas
from ..database import get_db

router = APIRouter()

@router.post("/providers/test-connection", response_model=schemas.ConnectionTestResponse, summary="测试连接")
async def test_connection(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，测试与外部 LLM 服务的连通性。
    """
    return await provider_service.test_connection_to_provider(api_host=request.apiHost, api_key=request.apiKey)


@router.post("/providers/fetch-models", response_model=List[schemas.AIModelBase], summary="获取外部模型列表")
async def fetch_models(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，从外部 LLM 服务获取可用的模型列表。
    """
    try:
        return await provider_service.fetch_models_from_provider(api_host=request.apiHost, api_key=request.apiKey)
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
    provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    try:
        return await provider_service.fetch_models_from_provider(api_host=provider.apiHost, api_key=provider.apiKey)
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

