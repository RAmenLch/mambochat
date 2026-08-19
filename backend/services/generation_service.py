# backend/services/generation_service.py

import json
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Tuple, Optional, Type, Dict

from backend.services.generation.executor.dispatcher import InstructionDispatcher
from backend.services.stream_manager_service import stream_manager
from backend.crud import chat_crud, message_crud, resource_crud, setting_crud
from backend import schemas
from backend.models import chat_model
from backend.database import AsyncSessionLocal
from backend.models.base_model import generate_uuid
from backend.services.generation.managers.default_manager import DefaultGenerateManager
from backend.services.generation.managers.title_manager import TitleGenerateManager
from backend.services.generation.managers.zip_history_manager import ZipHistoryGenerateManager

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.worker.chat_worker import UniversalGraphWorker
from backend.services.generation.worker.deep_agent_chat_worker import DeepAgentChatWorker
from backend.services.generation.worker.simple_worker import SimpleWorker

from backend.schemas.enums import FileManagementType, MessageStatus, MessageRole, SubMessageType, ProviderWorkerType, AgentTypeEnum, ChatMode
from backend.schemas.message import ErrorContent
from backend.config.timezone_config import get_configured_now, TZ
from backend.services.file_service import FileService
from backend.services.generation.agent.user_file_copy_service import process_user_message_files

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
                elif sm.type == SubMessageType.ASK_USER.value and sm.status == MessageStatus.PENDING_REVIEW.value:
                    try:
                        from backend.schemas.message import AskUserContent
                        content = AskUserContent.from_json_string(sm.content)
                        if content.answers is None:
                            return MessageStatus.PENDING_REVIEW
                    except (ValueError, ImportError):
                        continue

        if MessageStatus.GENERATING.value in sub_statuses:
            return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING
        if MessageStatus.FAILED.value in sub_statuses:
            return MessageStatus.FAILED

    if await stream_manager.is_stream_active(message.id):
        return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING

    if not message.sub_messages:
        created_at = message.createdAt
        if created_at.tzinfo is None:
            created_at = TZ.localize(created_at)

        time_since_creation = get_configured_now() - created_at
        if time_since_creation > GENERATION_START_TIMEOUT:
            return MessageStatus.FAILED

        return MessageStatus.COMPLETED if cancellation_requested else MessageStatus.GENERATING

    return MessageStatus.COMPLETED


async def prepare_for_regeneration(
        db: AsyncSession,
        chat_id: str,
        base_message_id: str,
) -> chat_model.Message:
    """
    准备重新生成：在指定的层级创建一个新的AI消息占位符分支。
    """
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot perform generation on a folder.")

    ref_message = await message_crud.get_message(db, message_id=base_message_id)
    if not ref_message or ref_message.chatId != chat_id:
        raise HTTPException(status_code=404, detail="Reference message not found in the specified chat.")

    if ref_message.role == MessageRole.ASSISTANT:
        target_parent_id = ref_message.parentId
    else:
        target_parent_id = ref_message.id

    assistant_message_create = schemas.MessageCreate(
        role=MessageRole.ASSISTANT,
        sub_messages=[],
        parentId=target_parent_id
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

    # 先创建消息和 SubMessage，再更新文管理类型，避免竞态条件：
    # 如果先更新 File.management_type 为 "sub_message"，在第二次 commit 之前，
    # cleanup_service 的 _cleanup_sub_message_files 会判定该 File 为孤儿并删除，
    # 导致用户消息中的图片异常消失。
    user_message_create = schemas.MessageCreate(
        role=MessageRole.USER,
        sub_messages=all_sub_messages
    )
    user_message = await message_crud.create_message(db, message=user_message_create, chat_id=chat_id)

    file_service = FileService(db)
    for sub_message in request.sub_messages:
        if sub_message.type == 'File':
            file_id = sub_message.content
            await file_service.update_management_type(
                file_id=file_id,
                new_type=FileManagementType.SUB_MESSAGE.value,
                merge=True
            )

    # Mambo Agent 会话：把用户文件副本写入 /.mambo/chat_user_file/ 并固化标志位
    await process_user_message_files(db, chat_id, user_message.id)

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


def _create_worker_instance(worker_type: str) -> AbstractGenerateWorker:
    return UniversalGraphWorker()


async def _get_worker_for_chat(db: AsyncSession, chat_id: str) -> AbstractGenerateWorker:
    """根据 Chat 绑定的 Agent 类型选择对应的 Worker。

    - DeepAgent → DeepAgentChatWorker（需要 VFS files 注入）【DEPRECATED：DeepAgent 已淘汰，仅兼容存量】
    - 其他（ReAct / Mambo / 无 Agent）→ UniversalGraphWorker
    """
    from backend.crud import agent_crud

    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)

    # DEPRECATED: DeepAgent 已淘汰，不再维护，此分支仅用于兼容存量数据
    if db_chat and db_chat.chatMode == ChatMode.AGENT.value and db_chat.agentId:
        agent = await agent_crud.get_agent(db, db_chat.agentId)
        if agent:
            agent_type = agent.AgentType
            if hasattr(agent_type, 'value'):
                agent_type = agent_type.value
            if agent_type == AgentTypeEnum.DEEP.value:
                return DeepAgentChatWorker()

    return UniversalGraphWorker()



async def _run_managed_generation_task(chat_id: str, assistant_message_id: str):
    """
    后台任务：协调整个生成过程。
    """
    async with AsyncSessionLocal() as db:
        final_status = None
        try:
            await _ensure_chat_model_configured(db, chat_id)

            worker = await _get_worker_for_chat(db, chat_id)
            manager = DefaultGenerateManager(db_session=db)
            executor = InstructionDispatcher(db_session=db)

            async for instruction in manager.run(worker, chat_id, assistant_message_id):
                exec_result = await executor.execute(instruction, chat_id, assistant_message_id)
                if isinstance(exec_result, MessageStatus):
                    final_status = exec_result

        except asyncio.CancelledError:
            print(f"[Generation Service] Task cancelled for message '{assistant_message_id}'.")
            final_status = MessageStatus.COMPLETED
        except Exception as e:
            print(f"[Generation Service Error] for message {assistant_message_id}: {e}")
            import traceback as tb
            final_status = MessageStatus.FAILED

            await db.rollback()

            try:
                error_content = ErrorContent(
                    message=f"生成流程发生异常: {e}",
                    stack_trace=tb.format_exc()
                )
                error_sub_message_create = schemas.SubMessageCreate(
                    id=generate_uuid(),
                    content=error_content.to_json_string(),
                    sortOrder=98,
                    type=SubMessageType.ERROR,
                    status=MessageStatus.FAILED
                )
                await message_crud.create_sub_message(db, assistant_message_id, error_sub_message_create)
                await db.commit()
            except Exception as inner_e:
                print(f"Failed to even create an error message for {assistant_message_id}: {inner_e}")

        finally:
            await stream_manager.mark_task_completed(assistant_message_id)
            await stream_manager.close_stream(assistant_message_id)
            await stream_manager.release_generation_lock(chat_id)


async def _run_retry_generation_task(chat_id: str, assistant_message_id: str):
    """
    后台任务：重试失败的生成任务，使用 LangGraph checkpoint 恢复。
    通过传入 input=None 和 thread_id 从 checkpoint 恢复图执行。
    """
    async with AsyncSessionLocal() as db:
        final_status = None
        try:
            await _ensure_chat_model_configured(db, chat_id)

            # 清理失败的子消息：删除 ERROR 类型以及 FAILED 的 NORMAL/REASONING，保留 FAILED 的 MCP_TOOL（用于 restore_state）
            db_message = await message_crud.get_message(db, message_id=assistant_message_id)
            if db_message:
                sub_ids_to_delete = []
                for sub in db_message.sub_messages:
                    if sub.type == SubMessageType.ERROR.value:
                        sub_ids_to_delete.append(sub.id)
                    elif sub.status == MessageStatus.FAILED.value and sub.type in (SubMessageType.NORMAL.value, SubMessageType.REASONING.value):
                        sub_ids_to_delete.append(sub.id)
                if sub_ids_to_delete:
                    for sub_id in sub_ids_to_delete:
                        sub = await db.get(chat_model.SubMessage, sub_id)
                        if sub:
                            await db.delete(sub)
                    await db.commit()

            worker = await _get_worker_for_chat(db, chat_id)
            manager = DefaultGenerateManager(db_session=db, recover_from_error=True)
            executor = InstructionDispatcher(db_session=db)

            async for instruction in manager.run(worker, chat_id, assistant_message_id):
                exec_result = await executor.execute(instruction, chat_id, assistant_message_id)
                if isinstance(exec_result, MessageStatus):
                    final_status = exec_result

        except asyncio.CancelledError:
            print(f"[Retry Generation Service] Task cancelled for message '{assistant_message_id}'.")
            final_status = MessageStatus.COMPLETED
        except Exception as e:
            print(f"[Retry Generation Service Error] for message {assistant_message_id}: {e}")
            import traceback as tb
            final_status = MessageStatus.FAILED

            await db.rollback()

            try:
                error_content = ErrorContent(
                    message=f"重试生成流程发生异常: {e}",
                    stack_trace=tb.format_exc()
                )
                error_sub_message_create = schemas.SubMessageCreate(
                    id=generate_uuid(),
                    content=error_content.to_json_string(),
                    sortOrder=98,
                    type=SubMessageType.ERROR,
                    status=MessageStatus.FAILED
                )
                await message_crud.create_sub_message(db, assistant_message_id, error_sub_message_create)
                await db.commit()
            except Exception as inner_e:
                print(f"Failed to even create an error message for {assistant_message_id}: {inner_e}")

        finally:
            await stream_manager.mark_task_completed(assistant_message_id)
            await stream_manager.close_stream(assistant_message_id)
            await stream_manager.release_generation_lock(chat_id)


async def run_title_generation_task(chat_id: str):
    """
    后台任务：为指定的会话生成并更新标题。
    """
    task_id = f"title-gen-{chat_id}"
    await stream_manager.mark_task_running(task_id)

    async with AsyncSessionLocal() as db:
        try:
            worker = SimpleWorker()

            manager = TitleGenerateManager(db_session=db)
            executor = InstructionDispatcher(db_session=db)

            async for instruction in manager.run(worker, chat_id, task_id):
                await executor.execute(
                    instruction=instruction,
                    chat_id=chat_id,
                    assistant_message_id=task_id
                )

        except Exception as e:
            print(f"[Title Generation Service Error] for chat {chat_id}: {e}")
            # 兜底：任务异常时也通知前端，避免前端 loading 永久卡住
            try:
                from backend.routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID
                await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, {
                    "type": "notification",
                    "category": "title_generation_error",
                    "context": {"chat_id": chat_id},
                    "level": "error",
                    "message": f"标题生成失败: {e}",
                })
            except Exception as notify_err:
                print(f"[Title Generation Service] Failed to publish error notification: {notify_err}")
        finally:
            await stream_manager.mark_task_completed(task_id)
            await stream_manager.close_stream(task_id)


async def run_zip_history_generation_task(chat_id: str, target_message_id: str):
    """
    后台任务：为指定消息之前的对话历史生成压缩摘要。
    """
    task_id = f"zip-history-gen-{target_message_id}"
    await stream_manager.mark_task_running(task_id)

    async with AsyncSessionLocal() as db:
        try:
            worker = SimpleWorker()
            manager = ZipHistoryGenerateManager(db_session=db)
            executor = InstructionDispatcher(db_session=db)

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
            await stream_manager.mark_task_completed(task_id)
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

    # 为 File 类型的子消息填充 file_info，以便前端在 SSE 流中立即加载图片
    file_ids = [sm.content for sm in message.sub_messages if sm.type == 'File' and sm.content]
    if file_ids:
        from backend.services.file_service import FileService
        file_service = FileService(db)
        file_records = await file_service.batch_get_files(file_ids)
        file_map = {f.id: file_service.convert_to_schema(f).model_dump(mode='json') for f in file_records}
        for sm_data in sub_messages_data:
            if sm_data.get('type') == 'File' and sm_data.get('content') in file_map:
                sm_data['file_info'] = file_map[sm_data['content']]

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
