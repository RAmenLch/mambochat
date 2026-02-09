# backend/services/provider_service.py

import httpx
import json
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import setting_crud
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS


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
        if api_host == "https://generativelanguage.googleapis.com/v1beta":
            func1 = fetch_models_from_provider_google
        else:
            func1 = fetch_models_from_provider

        await func1(db, api_host, api_key, use_proxy)
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
    调用外部LLM服务商的API以获取其提供的模型列表，并解析元数据。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{api_host.rstrip('/')}/models"

    # 创建一个包含所有系统支持的参数键的集合，用于高效查找
    valid_parameter_keys = {param.key for param in SUPPORTED_LLM_PARAMETERS}

    async with await _get_http_client_with_proxy(db, use_proxy_flag=use_proxy, timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        model_list = data.get("data", [])

        if not isinstance(model_list, list):
            raise json.JSONDecodeError("响应体中的 'data' 字段不是一个列表", str(data), 0)

        processed_models = []
        for model in model_list:
            if not (isinstance(model, dict) and model.get("id")):
                continue

            meta_dict = {}
            architecture = model.get('architecture', {}) or {}
            top_provider = model.get('top_provider', {}) or {}

            # 安全地提取所有潜在的元配置字段
            tokenizer = architecture.get('tokenizer')
            input_modalities = architecture.get('input_modalities')
            output_modalities = architecture.get('output_modalities')
            context_length = top_provider.get('context_length')
            max_output_tokens = top_provider.get('max_completion_tokens')
            supported_parameters = model.get('supported_parameters')

            # 仅当值有效时才将其添加到字典中
            if tokenizer: meta_dict['tokenizer'] = tokenizer
            if input_modalities: meta_dict['input_modalities'] = input_modalities
            if output_modalities: meta_dict['output_modalities'] = output_modalities
            if context_length is not None: meta_dict['context_length'] = context_length
            if max_output_tokens is not None: meta_dict['max_output_tokens'] = max_output_tokens

            # 过滤服务商返回的参数列表，仅保留系统支持的参数
            if supported_parameters and isinstance(supported_parameters, list):
                filtered_parameters = [
                    key for key in supported_parameters if key in valid_parameter_keys
                ]
                if filtered_parameters:
                    meta_dict['supported_parameters'] = filtered_parameters

            # 仅当 meta_dict 非空时才创建 meta_config 对象
            meta_config_obj = schemas.AIModelMetaConfig(**meta_dict) if meta_dict else None

            # 使用更友好的 "name" 字段（如果存在），否则回退到 "id"
            model_name = model.get("name", model.get("id"))

            processed_models.append(
                schemas.AIModelBase(
                    modelId=model.get("id"),
                    name=model_name,
                    meta_config=meta_config_obj
                )
            )
        return processed_models


async def fetch_models_from_provider_google(
        db: AsyncSession,
        api_host: str,
        api_key: str,
        use_proxy: bool
) -> List[schemas.AIModelBase]:
    """
    调用外部LLM服务商的API以获取其提供的模型列表，并解析元数据。
    """
    headers = {
        "Content-Type": "application/json",
    }

    url = f"{api_host.rstrip('/')}/models?key={api_key}"

    async with await _get_http_client_with_proxy(db, use_proxy_flag=use_proxy, timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # 1. 修改解析键名：Google 返回的是 'models' 而不是 'data'
        model_list = data.get("models", [])

        if not isinstance(model_list, list):
            raise json.JSONDecodeError("响应体中的 'models' 字段不是一个列表", str(data), 0)

        processed_models = []
        for model in model_list:
            # 2. 修改 ID 校验逻辑：Google 使用 'name' 字段作为唯一标识
            if not (isinstance(model, dict) and model.get("name")):
                continue

            meta_dict = {}

            # 3. 字段映射：将 Google 的字段映射到系统的 meta_config 结构
            # inputTokenLimit -> context_length
            input_token_limit = model.get('inputTokenLimit')
            if input_token_limit is not None:
                meta_dict['context_length'] = input_token_limit

            # outputTokenLimit -> max_output_tokens
            output_token_limit = model.get('outputTokenLimit')
            if output_token_limit is not None:
                meta_dict['max_output_tokens'] = output_token_limit

            # 注意：Google 响应中通常不直接提供 tokenizer, input_modalities 等信息，
            # 也没有 supported_parameters 列表（只有 supportedGenerationMethods）。
            # 这里我们只提取明确存在的数值字段。

            # 仅当 meta_dict 非空时才创建 meta_config 对象
            meta_config_obj = schemas.AIModelMetaConfig(**meta_dict) if meta_dict else None

            # 4. ID 与 Name 映射
            # modelId: 使用 Google 的 'name' (例如 'models/gemini-2.5-flash')
            # name: 使用 Google 的 'displayName' (例如 'Gemini 2.5 Flash')
            model_id = model.get("name")
            model_name = model.get("displayName", model_id)

            processed_models.append(
                schemas.AIModelBase(
                    modelId=model_id,
                    name=model_name,
                    meta_config=meta_config_obj
                )
            )
        return processed_models

