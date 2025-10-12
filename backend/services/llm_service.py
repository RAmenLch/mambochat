# backend/services/llm_service.py

import httpx
import json
import asyncio
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Tuple, Dict, Any, Optional

from .. import crud, schemas, models
from ..database import AsyncSessionLocal


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
        # 捕获其他未知异常，打印日志以供调试
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
    # 遵循OpenAI API规范，模型列表端点为 /models
    url = f"{api_host.rstrip('/')}/models"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()  # 如果状态码是 4xx 或 5xx, 将会抛出 HTTPStatusError

        # response.json() 可能会抛出 json.JSONDecodeError
        data = response.json()

        # 假设响应体格式为 {"data": [{"id": "model-id-1"}, ...]}
        model_list = data.get("data", [])

        if not isinstance(model_list, list):
            raise json.JSONDecodeError("响应体中的 'data' 字段不是一个列表", str(data), 0)

        return [
            schemas.AIModelBase(modelId=model.get("id"), name=model.get("id"))
            for model in model_list if isinstance(model, dict) and model.get("id")
        ]


def _prepare_llm_request_data(
        db_chat: models.Chat,
        history_messages: List[models.Message]
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    根据会话配置和历史消息，准备发送给 LLM API 的 headers 和 payload。
    """
    # 如果会话的模型被删除，ai_model会是None
    if not db_chat.ai_model or not db_chat.ai_model.provider:
        raise ValueError("会话未配置有效的AI模型或服务商。")

    provider = db_chat.ai_model.provider
    model = db_chat.ai_model

    headers = {
        "Authorization": f"Bearer {provider.apiKey}",
        "Content-Type": "application/json",
    }

    messages_payload = []
    if db_chat.systemPrompt:
        messages_payload.append({"role": "system", "content": db_chat.systemPrompt})

    for msg in history_messages:
        messages_payload.append({"role": msg.role, "content": msg.content})

    model_params = {}
    if db_chat.modelParameters:
        try:
            model_params = db_chat.modelParameters if isinstance(db_chat.modelParameters, dict) else json.loads(
                db_chat.modelParameters)
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not parse modelParameters for chat {db_chat.id}")
            pass

    # 从模型参数中移除自定义的 max_context_messages，避免发送给 LLM API
    model_params.pop('max_context_messages', None)

    payload = {
        "model": model.modelId,
        "messages": messages_payload,
        **model_params
    }

    return headers, payload, provider.apiHost


async def prepare_for_generation(
        db: AsyncSession,
        chat_id: str,
        user_content: Optional[str] = None,
        base_message_id: Optional[str] = None,
        save_user_message: bool = True,
) -> models.Message:
    """
    准备生成的前置操作：保存用户消息、删除后续历史、创建AI消息占位符。
    """
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot perform generation on a folder.")

    if save_user_message and user_content is not None:
        await crud.create_message(
            db,
            message=schemas.MessageCreate(content=user_content, role=schemas.MessageRole.USER),
            chat_id=chat_id
        )

    if base_message_id:
        ref_message = await crud.get_message(db, message_id=base_message_id)
        if not ref_message or ref_message.chatId != chat_id:
            raise HTTPException(status_code=404, detail="Reference message not found in the specified chat.")

        include_self = (ref_message.role == schemas.MessageRole.ASSISTANT)
        await crud.delete_messages_after(db, chat_id=chat_id, message_id=base_message_id, include_self=include_self)

    # 创建并返回空的 assistant 消息占位符
    assistant_message = await crud.create_message(
        db,
        message=schemas.MessageCreate(content="", role=schemas.MessageRole.ASSISTANT),
        chat_id=chat_id
    )
    return assistant_message


async def stream_chat_response(
        db: AsyncSession,
        chat_id: str,
        assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """
    核心流式函数：调用外部LLM API并流式返回响应，最后更新占位符消息。
    """
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        # 这种情况理论上不应发生，因为prepare阶段已经检查过
        print(f"Chat with id {chat_id} not found during streaming.")
        return

    # 如果会话没有模型，尝试应用全局默认模型
    if not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)
            db_chat = await crud.get_chat(db, chat_id=chat_id)
        else:
            error_msg = "**错误: 当前会话未指定模型，且未设置全局默认模型。**"
            yield f"data: {json.dumps(error_msg)}\n\n"
            async with AsyncSessionLocal() as final_db:
                await crud.update_message(
                    final_db, assistant_message_id, schemas.MessageUpdate(content=error_msg)
                )
            return

    full_response_content = ""
    try:
        # 解析模型参数以获取上下文消息数量限制
        model_params = {}
        if db_chat.modelParameters:
            try:
                model_params = json.loads(db_chat.modelParameters)
            except (json.JSONDecodeError, TypeError):
                pass

        max_messages = model_params.get('max_context_messages')
        limit = max_messages if isinstance(max_messages, int) and max_messages > 0 else None

        # 获取历史记录时，应排除我们刚创建的空assistant消息
        if limit:
            history_messages = await crud.get_limited_recent_messages(db, chat_id=chat_id, limit=limit + 1)
            history_messages = [msg for msg in history_messages if msg.id != assistant_message_id]
            if len(history_messages) > limit:
                history_messages = history_messages[-limit:]
        else:
            all_messages = await crud.get_messages_by_chat(db, chat_id=chat_id)
            history_messages = [msg for msg in all_messages if msg.id != assistant_message_id]

        try:
            headers, payload, api_host = _prepare_llm_request_data(db_chat, history_messages)
            payload["stream"] = True
        except ValueError as e:
            error_msg = f"**错误: {e}**"
            full_response_content = error_msg
            yield f"data: {json.dumps(error_msg)}\n\n"
            return

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{api_host.rstrip('/')}/chat/completions", headers=headers,
                                         json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices")

                                # 安全地处理数据块，仅当choices列表存在且非空时才提取内容
                                if choices and len(choices) > 0:
                                    delta = choices[0].get("delta", {})
                                    content_chunk = delta.get("content")
                                    if content_chunk:
                                        full_response_content += content_chunk
                                        yield f"data: {json.dumps(content_chunk)}\n\n"
                            except json.JSONDecodeError:
                                # 如果某一行不是有效的JSON，则忽略并继续
                                continue
        except httpx.HTTPStatusError as e:
            error_details = ""
            try:
                error_body = await e.response.aread()
                error_details = error_body.decode()
            except httpx.StreamClosed:
                error_details = f"HTTP {e.response.status_code} {e.response.reason_phrase}. (无法读取响应体，流已关闭)"
            error_msg = f'\n\n**错误: {error_details}**'
            full_response_content += error_msg
            yield f"data: {json.dumps(error_msg)}\n\n"
        except httpx.RequestError as e:
            error_msg = f'\n\n**错误: 无法连接到LLM服务商: {e}**'
            full_response_content += error_msg
            yield f"data: {json.dumps(error_msg)}\n\n"
        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):
                print(f"An unexpected error occurred: {str(e)}")
                error_msg = f'\n\n**错误: 发生未知异常: {e}**'
                full_response_content += error_msg
                yield f"data: {json.dumps(error_msg)}\n\n"
            else:
                print(
                    f"[BACKEND DEBUG] asyncio.CancelledError caught for chatId '{chat_id}'. This is likely due to client disconnecting.")
                raise
    finally:
        if full_response_content.strip():
            async def update_task():
                async with AsyncSessionLocal() as final_db:
                    print(
                        f"[BACKEND DEBUG] 'finally' block: Updating message '{assistant_message_id}' with final content.")
                    await crud.update_message(
                        final_db,
                        message_id=assistant_message_id,
                        message_update=schemas.MessageUpdate(content=full_response_content.strip())
                    )
                    print(f"[BACKEND DEBUG] Update complete for message '{assistant_message_id}'.")

            try:
                await asyncio.shield(update_task())
            except asyncio.CancelledError:
                print(
                    f"[BACKEND DEBUG] 'finally' block: Update task was cancelled before completion for message '{assistant_message_id}'.")
                pass


async def generate_chat_response_non_stream(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession,
        save_user_message: bool = True
) -> models.Message:
    """
    处理聊天请求，调用外部LLM API并以非流式一次性返回响应。
    """
    if save_user_message:
        await crud.create_message(
            db,
            message=schemas.MessageCreate(content=request.content, role=schemas.MessageRole.USER),
            chat_id=chat_id
        )

    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    # 如果会话没有模型，尝试应用全局默认模型
    if not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)
            db_chat = await crud.get_chat(db, chat_id=chat_id)
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前会话未指定模型，且未设置全局默认模型。")

    # 解析模型参数以获取上下文消息数量限制
    model_params = {}
    if db_chat.modelParameters:
        try:
            model_params = json.loads(db_chat.modelParameters)
        except (json.JSONDecodeError, TypeError):
            pass

    max_messages = model_params.get('max_context_messages')
    limit = max_messages if isinstance(max_messages, int) and max_messages > 0 else None

    if limit:
        history_messages = await crud.get_limited_recent_messages(db, chat_id=chat_id, limit=limit)
    else:
        history_messages = await crud.get_messages_by_chat(db, chat_id=chat_id)

    try:
        headers, payload, api_host = _prepare_llm_request_data(db_chat, history_messages)
        payload["stream"] = False
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    full_response_content = ""
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{api_host.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            full_response_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except httpx.RequestError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"无法连接到LLM服务商: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"发生未知异常: {str(e)}")

    if full_response_content:
        assistant_message = await crud.create_message(
            db,
            message=schemas.MessageCreate(content=full_response_content, role=schemas.MessageRole.ASSISTANT),
            chat_id=chat_id
        )
        return assistant_message
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="LLM服务商返回了空响应。")
