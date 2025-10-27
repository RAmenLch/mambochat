# backend/services/provider_service.py

import httpx
import json
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .. import schemas
from ..crud import setting_crud
from ..models import provider_model


async def _get_http_client_with_proxy(
    db: AsyncSession,
    use_proxy_flag: bool = False,
    timeout: int = 30
) -> httpx.AsyncClient:
    """
    根据需要创建一个配置了代理的 httpx.AsyncClient 实例。
    """
    proxy_url = None
    if use_proxy_flag:
        proxy_enabled_setting = await setting_crud.get_setting(db, "proxy_enabled")
        if proxy_enabled_setting and proxy_enabled_setting.value == 'True':
            proxy_url_setting = await setting_crud.get_setting(db, "proxy_url")
            if proxy_url_setting and proxy_url_setting.value:
                proxy_url = proxy_url_setting.value

    # 使用 'proxy' (单数) 参数, 它更简单且兼容性更好
    return httpx.AsyncClient(proxy=proxy_url, timeout=timeout)


async def test_proxy_connection(proxy_url: str, test_url: str) -> schemas.ConnectionTestResponse:
    """
    测试指定的代理服务器是否能成功访问一个测试URL。
    """
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=15) as client:
            response = await client.get(test_url, follow_redirects=True)
            response.raise_for_status()
        return schemas.ConnectionTestResponse(status="success", message="代理连接成功！")
    except httpx.HTTPStatusError as e:
        return schemas.ConnectionTestResponse(
            status="error",
            message=f"代理连接失败: 目标服务器返回错误码 {e.response.status_code}。"
        )
    except httpx.ProxyError as e:
        return schemas.ConnectionTestResponse(
            status="error",
            message=f"代理服务器错误: {e.__class__.__name__}。请检查代理地址和端口是否正确，以及代理服务是否正在运行。"
        )
    except httpx.RequestError as e:
        return schemas.ConnectionTestResponse(
            status="error",
            message=f"请求失败: 无法通过代理访问目标地址。请检查网络和目标地址。 ({type(e).__name__})"
        )
    except Exception as e:
        # 修复: BUG的根源在这里, 我们捕获'proxies'关键字错误, 但现在已经修复了它
        # 依然保留通用的异常捕获
        return schemas.ConnectionTestResponse(status="error", message=f"发生未知错误: {e}")


async def test_connection_to_provider(
    db: AsyncSession,
    api_host: str,
    api_key: str,
    use_proxy: bool
) -> schemas.ConnectionTestResponse:
    """
    测试与外部LLM服务商的连接，并可选择通过代理进行。
    """
    try:
        await fetch_models_from_provider(db, api_host, api_key, use_proxy)
        return schemas.ConnectionTestResponse(status="success", message="连接成功！")
    except json.JSONDecodeError:
        return schemas.ConnectionTestResponse(
            status="error",
            message="连接失败: 服务器返回的不是有效的JSON格式。请确认 API Host 是 API 的基础地址 (例如 https://api.openai.com/v1)，而不是一个网页地址。"
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_message = f"连接失败: 服务器返回错误码 {status_code}。"
        if status_code == 401:
            error_message += " API Key 无效或权限不足，请检查您的 API Key。"
        elif status_code == 404:
            error_message += " 无法找到模型接口。请确认 API Host 是正确的 API 基础地址。"
        return schemas.ConnectionTestResponse(status="error", message=error_message)
    except httpx.RequestError as e:
        return schemas.ConnectionTestResponse(
            status="error",
            message=f"连接失败: 无法访问 API Host。请检查网络连接或地址拼写是否正确。({type(e).__name__})"
        )
    except Exception as e:
        print(f"Unhandled exception during connection test: {e}")
        return schemas.ConnectionTestResponse(status="error", message=f"发生未知错误。")


async def fetch_models_from_provider(
    db: AsyncSession,
    api_host: str,
    api_key: str,
    use_proxy: bool
) -> List[schemas.AIModelBase]:
    """
    调用外部LLM服务商的API以获取其提供的模型列表，并可选择通过代理进行。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{api_host.rstrip('/')}/models"

    async with await _get_http_client_with_proxy(db, use_proxy_flag=use_proxy, timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        model_list = data.get("data", [])

        if not isinstance(model_list, list):
            raise json.JSONDecodeError("响应体中的 'data' 字段不是一个列表", str(data), 0)

        return [
            schemas.AIModelBase(modelId=model.get("id"), name=model.get("id"))
            for model in model_list if isinstance(model, dict) and model.get("id")
        ]
