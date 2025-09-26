# backend/services/llm_service.py

import httpx
import json
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

from .. import crud, schemas, models
from ..database import AsyncSessionLocal  # 【修复1】: 导入会话工厂

async def generate_chat_response(
        chat_id: str,
        request: schemas.GenerateRequest
        # 【修复2】: 移除 db: AsyncSession 参数
) -> AsyncGenerator[str, None]:
    """
    核心函数：处理聊天请求，调用外部LLM API并流式返回响应。
    """
    # 【修复3】: 手动创建和管理数据库会话，以匹配生成器的生命周期
    async with AsyncSessionLocal() as db:
        try:
            # 1. 保存用户的消息
            await crud.create_message(
                db,
                message=schemas.MessageCreate(content=request.content, role=schemas.MessageRole.USER),
                chat_id=chat_id
            )

            # 2. 获取完整的聊天上下文和配置
            db_chat = await crud.get_chat(db, chat_id=chat_id)
            if not db_chat:
                # 在流式响应中处理错误的一种方式是 yield 一个错误消息，但这里我们直接中断
                # 前端 onerror 会捕获到连接中断
                # 更优雅的方式是 yield 一个 SSE 错误事件
                print(f"Chat with id {chat_id} not found.")
                return

            if not db_chat.ai_model or not db_chat.ai_model.provider:
                print(f"Chat {chat_id} is not configured with a model.")
                return

            provider = db_chat.ai_model.provider
            model = db_chat.ai_model

            # 3. 准备发送给LLM API的请求数据
            headers = {
                "Authorization": f"Bearer {provider.apiKey}",
                "Content-Type": "application/json",
            }

            messages_payload = []
            if db_chat.systemPrompt:
                messages_payload.append({"role": "system", "content": db_chat.systemPrompt})

            # 注意：这里获取的是包含刚刚创建的用户消息在内的历史记录
            history_messages = await crud.get_messages_by_chat(db, chat_id=chat_id, limit=20)
            for msg in history_messages:
                messages_payload.append({"role": msg.role, "content": msg.content})

            model_params = {}
            if db_chat.modelParameters:
                try:
                    model_params = json.loads(db_chat.modelParameters)
                except json.JSONDecodeError:
                    pass

            payload = {
                "model": model.modelId,
                "messages": messages_payload,
                "stream": True,
                **model_params
            }

            # 4. 发起异步流式请求
            full_response_content = ""
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream("POST", f"{provider.apiHost}/chat/completions", headers=headers, json=payload) as response:
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
                                        # 【修复4】: 遵循SSE格式, 返回 data: ...\n\n
                                        # (您之前的代码是正确的，这里予以保留和确认)
                                        yield f"data: {json.dumps(content_chunk)}\n\n"
                                except json.JSONDecodeError:
                                    continue
            except httpx.HTTPStatusError as e:
                # 更具体地处理API错误
                error_details = e.response.text
                print(f"LLM provider returned an error: {e.response.status_code} - {error_details}")
                yield f"data: {json.dumps(f'\\n\\n**错误: {error_details}**')}\\n\\n"
            except httpx.RequestError as e:
                print(f"Failed to connect to LLM provider: {str(e)}")
                yield f"data: {json.dumps(f'\\n\\n**错误: 无法连接到LLM服务商: {e}**')}\\n\\n"
            except Exception as e:
                print(f"An unexpected error occurred: {str(e)}")
                yield f"data: {json.dumps(f'\\n\\n**错误: 发生未知异常: {e}**')}\\n\\n"


            # 5. 在流结束后，保存完整的AI回复
            if full_response_content:
                await crud.create_message(
                    db,
                    message=schemas.MessageCreate(content=full_response_content, role=schemas.MessageRole.ASSISTANT),
                    chat_id=chat_id
                )
        finally:
            # async with 会自动处理 session.close()
            pass


async def generate_chat_response_non_stream(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession
) -> models.Message:
    # (非流式函数保持不变)
    await crud.create_message(
        db,
        message=schemas.MessageCreate(content=request.content, role=schemas.MessageRole.USER),
        chat_id=chat_id
    )
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    if not db_chat.ai_model or not db_chat.ai_model.provider:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat is not configured with an AI model or provider."
        )

    provider = db_chat.ai_model.provider
    model = db_chat.ai_model
    headers = {
        "Authorization": f"Bearer {provider.apiKey}",
        "Content-Type": "application/json",
    }
    messages_payload = []
    if db_chat.systemPrompt:
        messages_payload.append({"role": "system", "content": db_chat.systemPrompt})
    history_messages = await crud.get_messages_by_chat(db, chat_id=chat_id, limit=20)
    for msg in history_messages:
        messages_payload.append({"role": msg.role, "content": msg.content})
    model_params = {}
    if db_chat.modelParameters:
        try:
            model_params = json.loads(db_chat.modelParameters)
        except json.JSONDecodeError:
            pass
    payload = {
        "model": model.modelId,
        "messages": messages_payload,
        "stream": False,
        **model_params
    }
    full_response_content = ""
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{provider.apiHost}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            full_response_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except httpx.RequestError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to connect to LLM provider: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

    if full_response_content:
        assistant_message = await crud.create_message(
            db,
            message=schemas.MessageCreate(content=full_response_content, role=schemas.MessageRole.ASSISTANT),
            chat_id=chat_id
        )
        return assistant_message
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM provider returned an empty response.")
