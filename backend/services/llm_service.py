# backend/services/llm_service.py

import httpx
import json
import asyncio  # <-- 新增导入
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Tuple, Dict, Any

from .. import crud, schemas, models
from ..database import AsyncSessionLocal


def _prepare_llm_request_data(
        db_chat: models.Chat,
        history_messages: List[models.Message]
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    根据会话配置和历史消息，准备发送给 LLM API 的 headers 和 payload。
    """
    if not db_chat.ai_model or not db_chat.ai_model.provider:
        raise ValueError("Chat is not configured with a valid AI model or provider.")

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

    payload = {
        "model": model.modelId,
        "messages": messages_payload,
        **model_params
    }

    return headers, payload, provider.apiHost


async def generate_chat_response(
        chat_id: str,
        request: schemas.GenerateRequest,
        save_user_message: bool = True
) -> AsyncGenerator[str, None]:
    """
    核心函数：处理聊天请求，调用外部LLM API并流式返回响应。
    采用“先创建占位，后更新内容”的策略，确保中断后内容能保存。
    """
    async with AsyncSessionLocal() as db:
        if save_user_message:
            await crud.create_message(
                db,
                message=schemas.MessageCreate(content=request.content, role=schemas.MessageRole.USER),
                chat_id=chat_id
            )
        assistant_message = await crud.create_message(
            db,
            message=schemas.MessageCreate(content="", role=schemas.MessageRole.ASSISTANT),
            chat_id=chat_id
        )
        db_chat = await crud.get_chat(db, chat_id=chat_id)
        if not db_chat:
            print(f"Chat with id {chat_id} not found.")
            return

    full_response_content = ""
    try:
        async with AsyncSessionLocal() as prep_db:
            history_messages = await crud.get_messages_by_chat(prep_db, chat_id=chat_id, limit=20)

        try:
            headers, payload, api_host = _prepare_llm_request_data(db_chat, history_messages)
            payload["stream"] = True
        except ValueError as e:
            error_msg = f"**错误: 准备请求时发生错误: {e}**"
            full_response_content = error_msg
            yield f"data: {json.dumps(error_msg)}\n\n"
            return

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{api_host}/chat/completions", headers=headers,
                                         json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content_chunk = delta.get("content")
                                if content_chunk:
                                    full_response_content += content_chunk
                                    yield f"data: {json.dumps(content_chunk)}\n\n"
                            except json.JSONDecodeError:
                                continue
        except httpx.HTTPStatusError as e:
            error_details = e.response.text
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
                raise  # 重新抛出 CancelledError 以便 finally 块可以处理
    finally:
        if assistant_message and full_response_content.strip():
            print(f"Saving content for message {assistant_message.id}. Content length: {len(full_response_content)}")

            # --- 核心修复: 使用 asyncio.shield 保护最终的数据库更新操作 ---
            async def update_task():
                async with AsyncSessionLocal() as final_db:
                    await crud.update_message(
                        final_db,
                        message_id=assistant_message.id,
                        message_update=schemas.MessageUpdate(content=full_response_content.strip())
                    )
                    print(f"Successfully saved content for message {assistant_message.id}.")

            try:
                # 即使此处的 await 被取消，update_task() 也会继续在后台运行完成
                await asyncio.shield(update_task())
            except asyncio.CancelledError:
                # 这是预期的行为，当客户端断开连接时，shield会抛出此异常
                # 但后台任务仍在运行，我们只需等待它完成即可
                print("Request cancelled, shielded update task is running in the background.")
                pass
        else:
            print(f"No content to save for message {assistant_message.id}.")


async def generate_chat_response_non_stream(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession
) -> models.Message:
    """
    处理聊天请求，调用外部LLM API并以非流式一次性返回响应。
    """
    await crud.create_message(
        db,
        message=schemas.MessageCreate(content=request.content, role=schemas.MessageRole.USER),
        chat_id=chat_id
    )
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    history_messages = await crud.get_messages_by_chat(db, chat_id=chat_id, limit=20)

    try:
        headers, payload, api_host = _prepare_llm_request_data(db_chat, history_messages)
        payload["stream"] = False
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    full_response_content = ""
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{api_host}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            full_response_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except httpx.RequestError as e:
        raise HTTPException(status_code=status.HTTP_5_02_BAD_GATEWAY,
                            detail=f"Failed to connect to LLM provider: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_5_00_INTERNAL_SERVER_ERROR,
                            detail=f"An unexpected error occurred: {str(e)}")

    if full_response_content:
        assistant_message = await crud.create_message(
            db,
            message=schemas.MessageCreate(content=full_response_content, role=schemas.MessageRole.ASSISTANT),
            chat_id=chat_id
        )
        return assistant_message
    raise HTTPException(status_code=status.HTTP_5_00_INTERNAL_SERVER_ERROR,
                        detail="LLM provider returned an empty response.")
