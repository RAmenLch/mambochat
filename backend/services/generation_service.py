# backend/services/generation_service.py

import json
import asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, List, Optional

from .stream_manager_service import stream_manager
from ..crud import chat_crud, message_crud
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

    assistant_message_create = schemas.MessageCreate(
        role=schemas.MessageRole.ASSISTANT,
        sub_messages=[] # 初始时不包含任何子消息
    )
    assistant_placeholder = await message_crud.create_message(db, message=assistant_message_create, chat_id=chat_id)
    return assistant_placeholder


async def _run_managed_generation_task(chat_id: str, assistant_message_id: str):
    """
    后台任务：协调整个生成过程。它实例化适当的 Worker 和 Manager，
    然后调用 manager.run() 来执行生成流程。
    """
    async with AsyncSessionLocal() as db:
        try:
            # 根据模型类型选择合适的Worker，目前只有OpenAI Worker
            worker = OpenAIGenerateWorker(db_session=db)
            manager = DefaultGenerateManager(db_session=db)

            # 调用Manager的run方法，它现在负责准备上下文和执行所有生成逻辑
            await manager.run(
                worker=worker,
                chat_id=chat_id,
                assistant_message_id=assistant_message_id
            )

        except asyncio.CancelledError:
            print(f"[Generation Service] Task cancelled for message '{assistant_message_id}'.")
            # Manager内部已处理了取消，这里仅作记录。
        except Exception as e:
            print(f"[Generation Service Error] for message {assistant_message_id}: {e}")
            # Manager内部已经处理了大部分异常，这里捕获的是Manager初始化或运行前可能发生的错误。
            # 尝试更新占位符消息以反映错误。
            try:
                error_sub_message_create = schemas.SubMessageCreate(
                    content=f"生成流程启动失败: {e}",
                    sortOrder=0,
                    type="Normal",
                    status=schemas.MessageStatus.FAILED
                )
                await message_crud.create_sub_message(db, assistant_message_id, error_sub_message_create)
            except Exception as inner_e:
                 print(f"Failed to even create an error message for {assistant_message_id}: {inner_e}")

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

    sub_messages_data = [schemas.SubMessage.model_validate(sm).model_dump(mode='json') for sm in message.sub_messages]
    initial_event_data = {"type": "replace", "sub_messages": sub_messages_data}
    yield f"data: {json.dumps(initial_event_data)}\n\n"

    has_sub_messages = len(message.sub_messages) > 0
    is_any_sub_generating = any(sm.status == chat_model.MessageStatus.GENERATING.value for sm in message.sub_messages)

    is_generation_definitely_finished = has_sub_messages and not is_any_sub_generating

    if is_generation_definitely_finished:
        return

    queue = await stream_manager.subscribe(assistant_message_id)
    try:
        while True:
            chunk_data = await queue.get()
            if chunk_data is None:
                break
            yield f"data: {json.dumps(chunk_data)}\n\n"
            queue.task_done()
    except asyncio.CancelledError:
        print(f"[Subscriber] Client disconnected for message '{assistant_message_id}'.")
    finally:
        await stream_manager.unsubscribe(assistant_message_id, queue)
