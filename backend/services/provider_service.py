# backend/services/provider_service.py

import httpx
import json
from typing import List

from .. import schemas

async def test_connection_to_provider(api_host: str, api_key: str) -> schemas.ConnectionTestResponse:
    """
    测试与外部LLM服务商的连接。
    通过尝试获取模型列表来验证API Host和API Key的有效性，并提供详细的错误反馈。
    """
    try:
        await fetch_models_from_provider(api_host, api_key)
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


async def fetch_models_from_provider(api_host: str, api_key: str) -> List[schemas.AIModelBase]:
    """
    调用外部LLM服务商的API以获取其提供的模型列表。
    此函数会抛出原始异常，由调用方处理。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{api_host.rstrip('/')}/models"

    async with httpx.AsyncClient(timeout=30) as client:
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

