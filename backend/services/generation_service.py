# backend/services/generation_service.py

import httpx
import json
import asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Tuple, Dict, Any, Optional

from .stream_manager_service import stream_manager
from ..crud import chat_crud, message_crud, setting_crud
from .. import schemas
from ..models import chat_model
from ..database import AsyncSessionLocal

async def prepare_for_generation(
        db: AsyncSession,
        chat_id: str,
        user_sub_messages: Optional[List[schemas.SubMessageCreate]] = None,
        base_message_id: Optional[str] = None,
        save_user_message: bool = True,
) -> chat_model.Message:
    """
    准备生成的前置操作：保存用户消息、删除后续历史、创建AI消息占位符。
    """
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot perform generation on a folder.")

    if save_user_message and user_sub_messages is not None:
        user_message_create = schemas.MessageCreate(
            role=schemas.MessageRole.USER,
            sub_messages=user_sub_messages
        )
        await message_crud.create_message(db, message=user_message_create, chat_id=chat_id)

    if base_message_id:
        ref_message = await message_crud.get_message(db, message_id=base_message_id)
        if not ref_message or ref_message.chatId != chat_id:
            raise HTTPException(status_code=404, detail="Reference message not found in the specified chat.")

        include_self = (ref_message.role == schemas.MessageRole.ASSISTANT)
        await message_crud.delete_messages_after(db, chat_id=chat_id, message_id=base_message_id, include_self=include_self)

    assistant_message_create = schemas.MessageCreate(
        role=schemas.MessageRole.ASSISTANT,
        sub_messages=[
            schemas.SubMessageCreate(
                content="",
                sortOrder=0,
                status=schemas.MessageStatus.GENERATING
            )
        ]
    )
    assistant_placeholder = await message_crud.create_message(db, message=assistant_message_create, chat_id=chat_id)
    return assistant_placeholder


def _prepare_llm_request_data(
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
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
        full_content = "\n".join(sub.content for sub in msg.sub_messages)
        messages_payload.append({"role": msg.role, "content": full_content})

    model_params = {}
    use_stream = True
    if db_chat.modelParameters:
        try:
            params_str = db_chat.modelParameters
            model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
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


async def _get_common_generation_context(db: AsyncSession, chat_id: str, assistant_message_id: str):
    """提取流式和非流式任务共用的上下文获取逻辑。"""
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise ValueError(f"Chat with id {chat_id} not found.")

    if not db_chat.aiModelId:
        default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)
            db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
        else:
            raise ValueError("当前会话未指定模型，且未设置全局默认模型。")

    model_params = {}
    if db_chat.modelParameters:
        try:
            params_str = db_chat.modelParameters
            model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
        except (json.JSONDecodeError, TypeError):
            pass

    max_messages = model_params.get('max_context_messages')
    limit = max_messages if isinstance(max_messages, int) and max_messages > 0 else None

    if limit:
        history_messages = await message_crud.get_limited_recent_messages(db, chat_id=chat_id, limit=limit + 1)
        history_messages = [msg for msg in history_messages if msg.id != assistant_message_id]
        if len(history_messages) > limit:
            history_messages = history_messages[-limit:]
    else:
        all_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        history_messages = [msg for msg in all_messages if msg.id != assistant_message_id]

    return db_chat, history_messages


async def run_generation_task_stream(chat_id: str, assistant_message_id: str):
    """后台任务：以流式方式调用LLM，并实时持久化和发布结果。"""
    async with AsyncSessionLocal() as db:
        final_status = schemas.MessageStatus.FAILED
        sub_message_id_to_update = None
        try:
            assistant_message = await message_crud.get_message(db, assistant_message_id)
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
                                        await message_crud.append_to_sub_message_content(db, sub_message_id_to_update, content_chunk)
                                        event_data = {"sub_message_id": sub_message_id_to_update, "content": content_chunk}
                                        await stream_manager.publish(assistant_message_id, event_data)
                            except json.JSONDecodeError:
                                continue
            final_status = schemas.MessageStatus.COMPLETED

        except Exception as e:
            print(f"[Stream Task Error] for message {assistant_message_id}: {e}")
            if sub_message_id_to_update:
                error_msg = f"\n\n**错误: {e}**"
                await message_crud.append_to_sub_message_content(db, sub_message_id_to_update, error_msg)
                event_data = {"sub_message_id": sub_message_id_to_update, "content": error_msg}
                await stream_manager.publish(assistant_message_id, event_data)
            final_status = schemas.MessageStatus.FAILED
        finally:
            if sub_message_id_to_update:
                await message_crud.update_sub_message_status(db, sub_message_id_to_update, final_status)
            await stream_manager.close_stream(assistant_message_id)


async def run_generation_task_non_stream(chat_id: str, assistant_message_id: str):
    """后台任务：以非流式方式调用LLM，获取完整响应后一次性持久化和发布。"""
    async with AsyncSessionLocal() as db:
        final_status = schemas.MessageStatus.FAILED
        sub_message_id_to_update = None
        try:
            assistant_message = await message_crud.get_message(db, assistant_message_id)
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
                await message_crud.update_sub_message(db, sub_message_id_to_update, update_schema)
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
                await message_crud.append_to_sub_message_content(db, sub_message_id_to_update, error_msg)
            final_status = schemas.MessageStatus.FAILED
        finally:
            if sub_message_id_to_update:
                await message_crud.update_sub_message_status(db, sub_message_id_to_update, final_status)
            await stream_manager.close_stream(assistant_message_id)


async def subscribe_to_stream(
        db: AsyncSession,
        assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """
    订阅一个生成流。首先发送历史内容，然后监听实时内容块。
    """
    message = await message_crud.get_message(db, assistant_message_id)
    if not message:
        return

    sub_messages_data = [schemas.SubMessage.model_validate(sm).model_dump(mode='json') for sm in message.sub_messages]

    initial_event_data = {"type": "replace", "sub_messages": sub_messages_data}
    yield f"data: {json.dumps(initial_event_data)}\n\n"

    is_still_generating = any(sm.status == chat_model.MessageStatus.GENERATING.value for sm in message.sub_messages)
    if not is_still_generating:
        return

    queue = await stream_manager.subscribe(assistant_message_id)
    try:
        while True:
            chunk_data = await queue.get()
            if chunk_data is None:
                break
            event_data = {"type": "append", **chunk_data}
            yield f"data: {json.dumps(event_data)}\n\n"
            queue.task_done()
    except asyncio.CancelledError:
        print(f"[Subscriber] Client disconnected for message '{assistant_message_id}'.")
    finally:
        await stream_manager.unsubscribe(assistant_message_id, queue)

