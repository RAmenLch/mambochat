# backend/services/generation_service.py

import json
import asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Optional

from .stream_manager_service import stream_manager
from ..crud import chat_crud, message_crud, setting_crud
from .. import schemas
from ..models import chat_model
from ..database import AsyncSessionLocal
from .generation.manager import DefaultGenerateManager
from .generation.openai_worker import OpenAIGenerateWorker


async def prepare_for_generation(
        db: AsyncSession,
        chat_id: str,
        user_sub_messages: Optional[List[schemas.SubMessageCreate]] = None,
        base_message_id: Optional[str] = None,
        save_user_message: bool = True,
) -> chat_model.Message:
    """
    准备生成的前置操作：保存用户消息、删除后续历史、创建AI消息占位符。
    AI消息占位符将不包含子消息，子消息的创建将由生成任务动态推送。
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

    # 创建一个空的assistant消息占位符，其sub_messages将由Manager动态创建
    assistant_message_create = schemas.MessageCreate(
        role=schemas.MessageRole.ASSISTANT,
        sub_messages=[] # 初始时不包含任何子消息
    )
    assistant_placeholder = await message_crud.create_message(db, message=assistant_message_create, chat_id=chat_id)
    return assistant_placeholder


async def _get_common_generation_context(db: AsyncSession, chat_id: str, assistant_message_id: str):
    """提取生成任务共用的上下文获取逻辑。"""
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise ValueError(f"Chat with id {chat_id} not found.")

    if not db_chat.aiModelId:
        default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)
            db_chat = await chat_crud.get_chat(db, chat_id=chat_id) # Refresh to get associated model/provider
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


async def _run_managed_generation_task(chat_id: str, assistant_message_id: str):
    """
    后台任务：协调LLM生成过程，使用Worker生成指令，Manager执行指令。
    """
    overall_status = schemas.MessageStatus.FAILED
    async with AsyncSessionLocal() as db:
        try:
            db_chat, history_messages = await _get_common_generation_context(db, chat_id, assistant_message_id)

            # 根据模型类型选择合适的Worker，目前只有OpenAI Worker
            worker = OpenAIGenerateWorker(db_session=db)
            manager = DefaultGenerateManager(db_session=db)

            overall_status = await manager.run(
                worker=worker,
                assistant_message_id=assistant_message_id,
                db_chat=db_chat,
                history_messages=history_messages
            )

        except asyncio.CancelledError:
            print(f"[Generation Service] Task cancelled for message '{assistant_message_id}'.")
            overall_status = schemas.MessageStatus.COMPLETED # Treat cancellation as completed for the message
        except Exception as e:
            print(f"[Generation Service Error] for message {assistant_message_id}: {e}")
            # 如果在Manager运行之前发生错误，或者Manager内部未捕获的错误，这里进行处理
            # 尝试更新assistant消息的整体状态
            assistant_message = await message_crud.get_message(db, assistant_message_id)
            if assistant_message:
                # 如果有任何子消息，更新其状态；如果没有，则创建一个错误子消息
                if assistant_message.sub_messages:
                    for sub_msg in assistant_message.sub_messages:
                        if sub_msg.status == schemas.MessageStatus.GENERATING.value:
                            await message_crud.update_sub_message_status(db, sub_msg.id, schemas.MessageStatus.FAILED)
                            # 确保错误信息被添加到某个子消息
                            if not sub_msg.content.endswith(f"\n\n**错误: {e}**"):
                                await message_crud.append_to_sub_message_content(db, sub_msg.id, f"\n\n**错误: {e}**")
                else:
                    # 如果没有子消息，创建一个错误子消息
                    error_sub_message_create = schemas.SubMessageCreate(
                        content=f"生成失败: {e}",
                        sortOrder=0,
                        type="Normal",
                        status=schemas.MessageStatus.FAILED
                    )
                    await message_crud.create_sub_message(db, assistant_message_id, error_sub_message_create)

            overall_status = schemas.MessageStatus.FAILED
        finally:
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

    # 发送初始的完整消息状态
    sub_messages_data = [schemas.SubMessage.model_validate(sm).model_dump(mode='json') for sm in message.sub_messages]
    initial_event_data = {"type": "replace", "sub_messages": sub_messages_data}
    yield f"data: {json.dumps(initial_event_data)}\n\n"

    # 检查是否有任何子消息仍在生成中
    is_still_generating = any(sm.status == chat_model.MessageStatus.GENERATING.value for sm in message.sub_messages)
    if not is_still_generating:
        # 如果所有子消息都已完成，则无需订阅实时流
        return

    queue = await stream_manager.subscribe(assistant_message_id)
    try:
        while True:
            chunk_data = await queue.get()
            if chunk_data is None: # 流结束的信号
                break
            # chunk_data 现在已经是 Manager 发布的结构化事件 (create, append, status_update)
            yield f"data: {json.dumps(chunk_data)}\n\n"
            queue.task_done()
    except asyncio.CancelledError:
        print(f"[Subscriber] Client disconnected for message '{assistant_message_id}'.")
    finally:
        await stream_manager.unsubscribe(assistant_message_id, queue)

