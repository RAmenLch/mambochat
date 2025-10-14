# backend/services/llm_service.py

import httpx
import json
import asyncio
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Tuple, Dict, Any, Optional

from .stream_manager import stream_manager
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


def _prepare_llm_request_data(
        db_chat: models.Chat,
        history_messages: List[models.Message]
) -> Tuple[Dict[str, Any], Dict[str, Any], str, bool]:
    """
    根据会话配置和历史消息，准备发送给 LLM API 的 headers, payload, host 和 stream 标志。
    """
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
        # 将多个SubMessage的内容合并为一个content字符串
        full_content = "\n".join(sub.content for sub in msg.sub_messages)
        messages_payload.append({"role": msg.role, "content": full_content})

    model_params = {}
    use_stream = True
    if db_chat.modelParameters:
        try:
            model_params = db_chat.modelParameters if isinstance(db_chat.modelParameters, dict) else json.loads(
                db_chat.modelParameters)
            if model_params.get('stream') is False:
                use_stream = False
        except (json.JSONDecodeError, TypeError):
            print(f"Warning: Could not parse modelParameters for chat {db_chat.id}")
            pass

    model_params.pop('max_context_messages', None)
    model_params.pop('stream', None)

    payload = {
        "model": model.modelId,
        "messages": messages_payload,
        **model_params
    }

    return headers, payload, provider.apiHost, use_stream


async def prepare_for_generation(
        db: AsyncSession,
        chat_id: str,
        user_sub_messages: Optional[List[schemas.SubMessageCreate]] = None,
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

    if save_user_message and user_sub_messages is not None:
        user_message_create = schemas.MessageCreate(
            role=schemas.MessageRole.USER,
            sub_messages=user_sub_messages
        )
        await crud.create_message(db, message=user_message_create, chat_id=chat_id)

    if base_message_id:
        ref_message = await crud.get_message(db, message_id=base_message_id)
        if not ref_message or ref_message.chatId != chat_id:
            raise HTTPException(status_code=404, detail="Reference message not found in the specified chat.")

        include_self = (ref_message.role == schemas.MessageRole.ASSISTANT)
        await crud.delete_messages_after(db, chat_id=chat_id, message_id=base_message_id, include_self=include_self)

    # 为AI助手的回复创建一个占位符，包含一个空的SubMessage
    assistant_message_create = schemas.MessageCreate(
        role=schemas.MessageRole.ASSISTANT,
        status=schemas.MessageStatus.GENERATING,
        sub_messages=[schemas.SubMessageCreate(content="", sortOrder=0)]
    )
    assistant_placeholder = await crud.create_message(db, message=assistant_message_create, chat_id=chat_id)
    return assistant_placeholder


async def _get_common_generation_context(db: AsyncSession, chat_id: str, assistant_message_id: str):
    """提取流式和非流式任务共用的上下文获取逻辑。"""
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise ValueError(f"Chat with id {chat_id} not found.")

    if not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)
            db_chat = await crud.get_chat(db, chat_id=chat_id)
        else:
            raise ValueError("当前会话未指定模型，且未设置全局默认模型。")

    model_params = {}
    if db_chat.modelParameters:
        try:
            model_params = json.loads(db_chat.modelParameters)
        except (json.JSONDecodeError, TypeError):
            pass

    max_messages = model_params.get('max_context_messages')
    limit = max_messages if isinstance(max_messages, int) and max_messages > 0 else None

    if limit:
        history_messages = await crud.get_limited_recent_messages(db, chat_id=chat_id, limit=limit + 1)
        history_messages = [msg for msg in history_messages if msg.id != assistant_message_id]
        if len(history_messages) > limit:
            history_messages = history_messages[-limit:]
    else:
        all_messages = await crud.get_messages_by_chat(db, chat_id=chat_id)
        history_messages = [msg for msg in all_messages if msg.id != assistant_message_id]

    return db_chat, history_messages


async def run_generation_task_stream(chat_id: str, assistant_message_id: str):
    """后台任务：以流式方式调用LLM，并实时持久化和发布结果。"""
    async with AsyncSessionLocal() as db:
        final_status = schemas.MessageStatus.FAILED
        sub_message_id_to_update = None
        try:
            assistant_message = await crud.get_message(db, assistant_message_id)
            if not assistant_message or not assistant_message.sub_messages:
                raise ValueError(f"Assistant placeholder message {assistant_message_id} or its sub_message not found.")
            sub_message_id_to_update = assistant_message.sub_messages[0].id

            db_chat, history_messages = await _get_common_generation_context(db, chat_id, assistant_message_id)
            headers, payload, api_host, _ = _prepare_llm_request_data(db_chat, history_messages)
            payload["stream"] = True

            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{api_host.rstrip('/')}/chat/completions", headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if await stream_manager.is_cancellation_requested(assistant_message_id):
                            print(f"[Stream Task] Cancellation detected for {assistant_message_id}. Stopping.")
                            break

                        if line.startswith("data:"):
                            data_str = line[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices")
                                if choices and len(choices) > 0:
                                    delta = choices[0].get("delta", {})
                                    content_chunk = delta.get("content")
                                    if content_chunk:
                                        await crud.append_to_sub_message_content(db, sub_message_id_to_update, content_chunk)
                                        event_data = {"sub_message_id": sub_message_id_to_update, "content": content_chunk}
                                        await stream_manager.publish(assistant_message_id, event_data)
                            except json.JSONDecodeError:
                                continue
            final_status = schemas.MessageStatus.COMPLETED

        except Exception as e:
            print(f"[Stream Task Error] for message {assistant_message_id}: {e}")
            if sub_message_id_to_update:
                error_msg = f"\n\n**错误: {e}**"
                await crud.append_to_sub_message_content(db, sub_message_id_to_update, error_msg)
                event_data = {"sub_message_id": sub_message_id_to_update, "content": error_msg}
                await stream_manager.publish(assistant_message_id, event_data)
            final_status = schemas.MessageStatus.FAILED
        finally:
            await crud.update_message_status(db, assistant_message_id, final_status)
            await stream_manager.close_stream(assistant_message_id)


async def run_generation_task_non_stream(chat_id: str, assistant_message_id: str):
    """后台任务：以非流式方式调用LLM，获取完整响应后一次性持久化和发布。"""
    async with AsyncSessionLocal() as db:
        final_status = schemas.MessageStatus.FAILED
        sub_message_id_to_update = None
        try:
            assistant_message = await crud.get_message(db, assistant_message_id)
            if not assistant_message or not assistant_message.sub_messages:
                raise ValueError(f"Assistant placeholder message {assistant_message_id} or its sub_message not found.")
            sub_message_id_to_update = assistant_message.sub_messages[0].id

            if await stream_manager.is_cancellation_requested(assistant_message_id):
                raise asyncio.CancelledError("Task was cancelled before starting.")

            db_chat, history_messages = await _get_common_generation_context(db, chat_id, assistant_message_id)
            headers, payload, api_host, _ = _prepare_llm_request_data(db_chat, history_messages)
            payload["stream"] = False

            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(f"{api_host.rstrip('/')}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                full_response_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if full_response_content:
                update_schema = schemas.SubMessageUpdate(content=full_response_content)
                await crud.update_sub_message(db, sub_message_id_to_update, update_schema)
                final_status = schemas.MessageStatus.COMPLETED
            else:
                raise ValueError("LLM服务商返回了空响应。")

        except asyncio.CancelledError:
            print(f"[Non-Stream Task] Cancellation detected for {assistant_message_id}. Stopping.")
            final_status = schemas.MessageStatus.COMPLETED
        except Exception as e:
            print(f"[Non-Stream Task Error] for message {assistant_message_id}: {e}")
            if sub_message_id_to_update:
                error_msg = f"\n\n**错误: {e}**"
                await crud.append_to_sub_message_content(db, sub_message_id_to_update, error_msg)
            final_status = schemas.MessageStatus.FAILED
        finally:
            await crud.update_message_status(db, assistant_message_id, final_status)
            await stream_manager.close_stream(assistant_message_id)


async def subscribe_to_stream(
        db: AsyncSession,
        assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """
    订阅一个生成流。首先发送历史内容，然后监听实时内容块。
    """
    message = await crud.get_message(db, assistant_message_id)
    if not message:
        return

    # 发送初始状态
    sub_messages_data = [schemas.SubMessage.model_validate(sm).model_dump() for sm in message.sub_messages]
    initial_event_data = {"type": "replace", "sub_messages": sub_messages_data}
    yield f"data: {json.dumps(initial_event_data)}\n\n"

    if message.status in [schemas.MessageStatus.COMPLETED, schemas.MessageStatus.FAILED]:
        return

    queue = await stream_manager.subscribe(assistant_message_id)
    try:
        while True:
            chunk_data = await queue.get()
            if chunk_data is None:
                break
            # chunk_data is expected to be a dict like {"sub_message_id": ..., "content": ...}
            event_data = {"type": "append", **chunk_data}
            yield f"data: {json.dumps(event_data)}\n\n"
            queue.task_done()
    except asyncio.CancelledError:
        print(f"[Subscriber] Client disconnected for message '{assistant_message_id}'.")
    finally:
        await stream_manager.unsubscribe(assistant_message_id, queue)
