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


async def _fetch_models_and_handle_errors(
        api_host: str,
        api_key: str,
        source_description: str
) -> List[schemas.AIModelBase]:
    """
    一个内部辅助函数，封装了调用服务获取模型并统一处理各种潜在异常的逻辑。

    Args:
        api_host: 目标API的主机地址。
        api_key: 用于认证的API密钥。
        source_description: 描述凭证来源的字符串，用于生成特定上下文的错误消息。

    Raises:
        HTTPException: 在发生连接错误、认证失败或响应解析错误时抛出。

    Returns:
        成功时返回模型列表。
    """
    try:
        return await provider_service.fetch_models_from_provider(api_host=api_host, api_key=api_key)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取模型失败: 服务器返回的不是有效的JSON格式。请检查{source_description}是否正确。"
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        detail = f"获取模型失败: 服务器返回错误码 {status_code}。"
        key_description = source_description.replace('Host', 'Key')
        if status_code == 401:
            detail += f" {key_description}无效或权限不足。"
        elif status_code == 404:
            detail += f" 找不到模型接口，请检查{source_description}。"
        raise HTTPException(status_code=status_code, detail=detail)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"获取模型失败: 无法连接到 API Host。({type(e).__name__})"
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取模型失败: 发生未知错误。")


@router.post("/providers/test-connection", response_model=schemas.ConnectionTestResponse, summary="测试连接")
async def test_connection(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，测试与外部 LLM 服务的连通性。
    """
    return await provider_service.test_connection_to_provider(api_host=request.apiHost, api_key=request.apiKey)


@router.post("/providers/{provider_id}/test-connection", response_model=schemas.ConnectionTestResponse, summary="为现有服务商测试连接")
async def test_connection_for_provider(
    provider_id: str,
    request: schemas.ConnectionTestForExistingProviderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    使用已存储的 API Key 为指定服务商测试连通性。
    API Host 从请求体中获取，以允许用户在前端修改后进行测试。
    """
    provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    # 使用请求中提供的 apiHost 和数据库中存储的 apiKey 进行测试
    return await provider_service.test_connection_to_provider(api_host=request.apiHost, api_key=provider.apiKey)


@router.post("/providers/fetch-models", response_model=List[schemas.AIModelBase], summary="获取外部模型列表")
async def fetch_models(request: schemas.ConnectionRequest):
    """
    根据提供的 API Host 和 Key，从外部 LLM 服务获取可用的模型列表。
    """
    return await _fetch_models_and_handle_errors(
        api_host=request.apiHost,
        api_key=request.apiKey,
        source_description="API Host"
    )


@router.get("/providers/{provider_id}/fetch-models", response_model=List[schemas.AIModelBase], summary="为现有服务商获取模型")
async def fetch_models_for_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    """
    使用已存储的凭证，为指定的服务商获取可用的模型列表。
    """
    provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return await _fetch_models_and_handle_errors(
        api_host=provider.apiHost,
        api_key=provider.apiKey,
        source_description="保存的 API Host"
    )

