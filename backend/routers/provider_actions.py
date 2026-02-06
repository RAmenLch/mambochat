# backend/routers/provider_actions.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import httpx
import json

from backend.services import provider_service
from backend.crud import provider_crud
from backend import schemas
from backend.database import get_db

router = APIRouter()


async def _fetch_models_and_handle_errors(
        db: AsyncSession,
        api_host: str,
        api_key: str,
        use_proxy: bool,
        source_description: str
) -> List[schemas.AIModelBase]:
    """
    一个内部辅助函数，封装了调用服务获取模型并统一处理各种潜在异常的逻辑。
    """
    try:
        if api_host == "https://generativelanguage.googleapis.com/v1beta":
            func1 = provider_service.fetch_models_from_provider_google
        else:
            func1 = provider_service.fetch_models_from_provider
        return await func1(db, api_host, api_key, use_proxy)
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
async def test_connection(
    request: schemas.ConnectionRequest,
    use_proxy: bool = False, # 允许前端在测试新连接时决定是否使用代理
    db: AsyncSession = Depends(get_db)
):
    """
    根据提供的 API Host 和 Key，测试与外部 LLM 服务的连通性。
    """
    return await provider_service.test_connection_to_provider(
        db=db,
        api_host=request.apiHost,
        api_key=request.apiKey,
        use_proxy=use_proxy
    )


@router.post("/providers/{provider_id}/test-connection", response_model=schemas.ConnectionTestResponse, summary="为现有服务商测试连接")
async def test_connection_for_provider(
    provider_id: str,
    request: schemas.ConnectionTestForExistingProviderRequest,
    use_proxy: bool, # 从前端实时获取代理选项
    db: AsyncSession = Depends(get_db)
):
    """
    使用已存储的 API Key 为指定服务商测试连通性。
    API Host 和 use_proxy 状态从请求中获取，以反映前端的实时编辑状态。
    """
    provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    return await provider_service.test_connection_to_provider(
        db=db,
        api_host=request.apiHost,
        api_key=provider.apiKey,
        use_proxy=use_proxy
    )


@router.post("/providers/fetch-models", response_model=List[schemas.AIModelBase], summary="获取外部模型列表")
async def fetch_models(
    request: schemas.ConnectionRequest,
    use_proxy: bool = False, # 允许前端在获取模型时决定是否使用代理
    db: AsyncSession = Depends(get_db)
):
    """
    根据提供的 API Host 和 Key，从外部 LLM 服务获取可用的模型列表。
    """
    return await _fetch_models_and_handle_errors(
        db=db,
        api_host=request.apiHost,
        api_key=request.apiKey,
        use_proxy=use_proxy,
        source_description="API Host"
    )


@router.get("/providers/{provider_id}/fetch-models", response_model=List[schemas.AIModelBase], summary="为现有服务商获取模型")
async def fetch_models_for_provider(
    provider_id: str,
    use_proxy: bool, # 从前端实时获取代理选项
    db: AsyncSession = Depends(get_db)
):
    """
    使用已存储的凭证，为指定的服务商获取可用的模型列表。
    use_proxy 状态从请求中获取，以反映前端的实时编辑状态。
    """
    provider = await provider_crud.get_provider(db, provider_id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return await _fetch_models_and_handle_errors(
        db=db,
        api_host=provider.apiHost,
        api_key=provider.apiKey,
        use_proxy=use_proxy,
        source_description="保存的 API Host"
    )
