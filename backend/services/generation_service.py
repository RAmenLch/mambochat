# backend/services/generation_service.py

import json
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Tuple, List, Optional

from backend.services.stream_manager_service import stream_manager
from backend.crud import chat_crud, message_crud, resource_crud, setting_crud, provider_crud
from backend import schemas
from backend.models import chat_model
from backend.database import AsyncSessionLocal
from backend.services.generation.instruction_executor import InstructionExecutor
from backend.models.base_model import generate_uuid
from backend.services.generation.default_manager import DefaultGenerateManager
from backend.services.generation.title_manager import TitleGenerateManager
from backend.services.generation.zip_history_manager import ZipHistoryGenerateManager
from backend.services.generation.worker.openai_worker import OpenAiWorker
from backend.services.generation.worker.google_worker import GoogleWorker
from backend.services.generation.worker.deepseek_worker import DeepSeekWorker
from backend.schemas.enums import FileManagementType, MessageStatus, MessageRole, SubMessageType, ProviderWorkerType
from backend.config.timezone_config import get_configured_now, TZ
from backend.services.generation.worker.anthropic_worker import AnthropicWorker
from backend.services.file_service import FileService

GENERATION_START_TIMEOUT = timedelta(minutes=10)


async def _calculate_message_status(message: chat_model.Message) -> schemas.MessageStatus:
    """
    根据消息的角色、子消息状态和活跃流状态，动态计算消息的聚合状态。
    """
    if message.role != MessageRole.ASSISTANT:
        return MessageStatus.COMPLETED

    cancellation_requested = await stream_manager.is_cancellation_requested(message.id)

    if await stream_manager.is_task_running(message.id):
        return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING

    # 1. 基于子消息状态判断
    if message.sub_messages:
        sub_statuses = {sm.status for sm in message.sub_messages}

        if MessageStatus.PENDING_REVIEW.value in sub_statuses:
            for sm in message.sub_messages:
                if sm.type == SubMessageType.REVIEW_TOOL.value and sm.status == MessageStatus.PENDING_REVIEW.value:
                    try:
                        from backend.schemas.message import ReviewToolContent
                        content = ReviewToolContent.from_json_string(sm.content)
                        if content.decision is None:
                            return MessageStatus.PENDING_REVIEW
                    except (ValueError, ImportError):
                        continue

        if MessageStatus.GENERATING.value in sub_statuses:
            return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING
        if MessageStatus.FAILED.value in sub_statuses:
            return MessageStatus.FAILED

    # 2. 检查是否有活跃的流
    if await stream_manager.is_stream_active(message.id):
        return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING

    # 3. 无活跃流，且没有任何子消息，检查是否超时
    if not message.sub_messages:
        created_at = message.createdAt
        if created_at.tzinfo is None:
            created_at = TZ.localize(created_at)

        time_since_creation = get_configured_now() - created_at
        if time_since_creation > GENERATION_START_TIMEOUT:
            return MessageStatus.FAILED

        return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING

    # 4. 有子消息，且没有 generating/failed/pending_review，且流已关闭
    return MessageStatus.COMPLETED


async def prepare_for_regeneration(
        db: AsyncSession,
        chat_id: str,
        base_message_id: str,
) -> chat_model.Message:
    """
    准备重新生成：删除指定消息之后的所有消息，并创建一个新的AI消息占位符。
    """
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot perform generation on a folder.")

    ref_message = await message_crud.get_message(db, message_id=base_message_id)
    if not ref_message or ref_message.chatId != chat_id:
        raise HTTPException(status_code=404, detail="Reference message not found in the specified chat.")

    include_self = (ref_message.role == MessageRole.ASSISTANT)
    await message_crud.delete_messages_after(db, chat_id=chat_id, message_id=base_message_id, include_self=include_self)

    assistant_message_create = schemas.MessageCreate(
        role=MessageRole.ASSISTANT,
        sub_messages=[]
    )
    assistant_placeholder = await message_crud.create_message(db, message=assistant_message_create, chat_id=chat_id)
    return assistant_placeholder


async def create_user_message_and_prepare_generation(
        db: AsyncSession,
        chat_id: str,
        request: schemas.GenerateRequest,
) -> Tuple[chat_model.Message, chat_model.Message]:
    """
    处理发送新消息的场景：创建用户消息，然后准备生成AI回复。
    返回一个元组 (新创建的用户消息, AI占位符消息)。
    """
    injected_sub_messages = []
    if request.attachedSubmessageResourceIds:
        for resource_id in request.attachedSubmessageResourceIds:
            resource = await resource_crud.get_resource(db, resource_id=resource_id)
            if resource and resource.latest_version and resource.resourceType == 'submessage_template':
                latest_version = resource.latest_version
                config_data = latest_version.attributes or {}

                template_sub_message = schemas.SubMessageCreate(
                    content=latest_version.content or "",
                    sortOrder=-1,
                    type=SubMessageType.NORMAL,
                    config=schemas.SubMessageConfig(**config_data),
                    status=MessageStatus.COMPLETED
                )
                injected_sub_messages.append(template_sub_message)

    all_sub_messages = injected_sub_messages + request.sub_messages
    for i, sub_msg in enumerate(all_sub_messages):
        sub_msg.sortOrder = i

    file_service = FileService(db)
    for sub_message in request.sub_messages:
        if sub_message.type == 'File':
            file_id = sub_message.content
            await file_service.update_management_type(
                file_id=file_id,
                new_type=FileManagementType.SUB_MESSAGE.value,
                merge=True
            )

    user_message_create = schemas.MessageCreate(
        role=MessageRole.USER,
        sub_messages=all_sub_messages
    )
    user_message = await message_crud.create_message(db, message=user_message_create, chat_id=chat_id)

    assistant_placeholder = await prepare_for_regeneration(db, chat_id, user_message.id)

    return user_message, assistant_placeholder


async def _ensure_chat_model_configured(db: AsyncSession, chat_id: str) -> None:
    """确保会话配置了 AI 模型，如果没有，尝试使用全局默认配置进行修补"""
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        return

    if not db_chat.aiModelId:
        default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value
            await db.commit()
            await db.refresh(db_chat)


def _create_worker_instance(worker_type: str):
    """Worker 工厂方法"""
    if worker_type == ProviderWorkerType.GOOGLE:
        return GoogleWorker()
    elif worker_type == ProviderWorkerType.DEEPSEEK:
        return DeepSeekWorker()
    elif worker_type == ProviderWorkerType.ANTHROPIC:
        return AnthropicWorker()
    else:
        return OpenAiWorker()


async def _get_worker_for_chat(db: AsyncSession, chat_id: str):
    """
    根据会话配置的服务商类型，返回对应的 Worker 实例。
    """
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    worker_type = ProviderWorkerType.OPENAI
    if db_chat and db_chat.ai_model and db_chat.ai_model.provider:
        worker_type = db_chat.ai_model.provider.worker_type

    return _create_worker_instance(worker_type)


async def _get_worker_from_settings(db: AsyncSession, setting_keys: List[str]):
    """
    根据全局设置列表（按优先级）查找模型，并返回对应的 Worker 实例。
    """
    target_model_id = None

    for key in setting_keys:
        setting = await setting_crud.get_setting(db, key)
        if setting and setting.value:
            target_model_id = setting.value
            break

    worker_type = ProviderWorkerType.OPENAI

    if target_model_id:
        model = await provider_crud.get_model(db, target_model_id)
        if model and model.provider:
            worker_type = model.provider.worker_type

    return _create_worker_instance(worker_type)


async def _run_managed_generation_task(chat_id: str, assistant_message_id: str):
    """
    后台任务：协调整个生成过程。
    """
    from backend.checkpointer import adelete_thread
    async with AsyncSessionLocal() as db:
        final_status = None
        try:
            await _ensure_chat_model_configured(db, chat_id)

            worker = await _get_worker_for_chat(db, chat_id)
            manager = DefaultGenerateManager(db_session=db)
            executor = InstructionExecutor(db_session=db)

            async for instruction in manager.run(worker, chat_id, assistant_message_id):
                exec_result = await executor.execute(
                    instruction=instruction,
                    chat_id=chat_id,
                    assistant_message_id=assistant_message_id
                )
                if isinstance(exec_result, MessageStatus):
                    final_status = exec_result

        except asyncio.CancelledError:
            print(f"[Generation Service] Task cancelled for message '{assistant_message_id}'.")
            final_status = MessageStatus.COMPLETED
        except Exception as e:
            print(f"[Generation Service Error] for message {assistant_message_id}: {e}")
            final_status = MessageStatus.FAILED
            try:
                error_sub_message_create = schemas.SubMessageCreate(
                    id=generate_uuid(),
                    content=f"生成流程发生异常: {e}",
                    sortOrder=0,
                    type=SubMessageType.NORMAL,
                    status=MessageStatus.FAILED
                )
                await message_crud.create_sub_message(db, assistant_message_id, error_sub_message_create)
            except Exception as inner_e:
                print(f"Failed to even create an error message for {assistant_message_id}: {inner_e}")

        finally:
            await stream_manager.mark_task_completed(assistant_message_id)
            await stream_manager.close_stream(assistant_message_id)
            if final_status in [MessageStatus.COMPLETED, MessageStatus.FAILED]:
                asyncio.create_task(adelete_thread(assistant_message_id))


async def run_title_generation_task(chat_id: str):
    """
    后台任务：为指定的会话生成并更新标题。
    """
    task_id = f"title-gen-{chat_id}"
    async with AsyncSessionLocal() as db:
        try:
            worker = await _get_worker_from_settings(db, ["title_generation_model_id", "default_model_id"])

            manager = TitleGenerateManager(db_session=db)
            executor = InstructionExecutor(db_session=db)

            async for instruction in manager.run(worker, chat_id, task_id):
                await executor.execute(
                    instruction=instruction,
                    chat_id=chat_id,
                    assistant_message_id=task_id
                )

        except Exception as e:
            print(f"[Title Generation Service Error] for chat {chat_id}: {e}")
        finally:
            await stream_manager.close_stream(task_id)


async def run_zip_history_generation_task(chat_id: str, target_message_id: str):
    """
    后台任务：为指定消息之前的对话历史生成压缩摘要。
    """
    task_id = f"zip-history-gen-{target_message_id}"
    async with AsyncSessionLocal() as db:
        try:
            worker = await _get_worker_for_chat(db, chat_id)
            manager = ZipHistoryGenerateManager(db_session=db)
            executor = InstructionExecutor(db_session=db)

            target_message = await message_crud.get_message(db, target_message_id)
            if target_message:
                for sub in target_message.sub_messages:
                    if sub.type == SubMessageType.ZIP_HISTORY.value:
                        manager.sub_message_id = sub.id

                        try:
                            config_obj = json.loads(sub.config) if isinstance(sub.config, str) else sub.config or {}
                            if config_obj.get('zip_enable') is True:
                                config_obj['zip_enable'] = False
                                update_schema = schemas.message.SubMessageUpdate(
                                    config=schemas.message.SubMessageConfig(**config_obj)
                                )
                                await message_crud.update_sub_message(db, sub.id, update_schema)
                        except (json.JSONDecodeError, TypeError):
                            pass
                        break

            async for instruction in manager.run(worker, chat_id, target_message_id):
                await executor.execute(
                    instruction=instruction,
                    chat_id=chat_id,
                    assistant_message_id=target_message_id
                )

        except Exception as e:
            print(f"[Zip History Generation Service Error] for message {target_message_id}: {e}")
        finally:
            await stream_manager.close_stream(task_id)


async def subscribe_to_stream(
        db: AsyncSession,
        assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """
    订阅一个生成流。首先发送历史内容和当前聚合状态，然后监听实时内容块。
    """
    message = await message_crud.get_message(db, assistant_message_id)
    if not message:
        return

    calculated_status = await _calculate_message_status(message)

    sub_messages_data = [schemas.SubMessage.model_validate(sm).model_dump(mode='json') for sm in message.sub_messages]
    initial_event_data = {
        "type": "replace",
        "sub_messages": sub_messages_data,
        "status": calculated_status.value
    }
    yield f"data: {json.dumps(initial_event_data)}\n\n"

    if calculated_status in [MessageStatus.COMPLETED, MessageStatus.FAILED]:
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
