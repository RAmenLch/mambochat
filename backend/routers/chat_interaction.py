# backend/routers/chat_interaction.py

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from typing import List

from backend.services import generation_service
from backend.services.stream_manager_service import stream_manager
from backend.services.file_service import FileService
from backend.crud import chat_crud, message_crud, setting_crud
from backend import schemas
from backend.models import chat_model
from backend.database import get_db
from backend.routers.chat_management import _apply_default_model_to_chat_object
from backend.schemas import SubMessageType, MessageStatus
from backend.schemas.message import ToolApprovalRequest

from pydantic import BaseModel

class TaskStatusRequest(BaseModel):
    task_ids: List[str]

class TaskStatusResponse(BaseModel):
    running_tasks: List[str]


class AskUserAnswerRequest(BaseModel):
    sub_message_id: str
    answers: List[str]
    ask_status: str = "answered"


router = APIRouter()



@router.post(
    "/tasks/status",
    response_model=TaskStatusResponse,
    summary="批量查询后台任务是否在运行",
    tags=["Tasks"]
)
async def check_tasks_status(request: TaskStatusRequest):
    """
    用于前端断线重连时对齐后台异步任务的状态。
    """
    running = []
    for tid in request.task_ids:
        if await stream_manager.is_task_running(tid):
            running.append(tid)
    return TaskStatusResponse(running_tasks=running)






async def _start_generation_task(
        background_tasks: BackgroundTasks,
        chat_id: str,
        assistant_message_id: str,
        is_retry: bool = False
):
    await stream_manager.mark_task_running(assistant_message_id)
    if is_retry:
        background_tasks.add_task(generation_service._run_retry_generation_task, chat_id, assistant_message_id)
    else:
        background_tasks.add_task(generation_service._run_managed_generation_task, chat_id, assistant_message_id)


async def _hydrate_and_validate_messages(
        db_messages: List[chat_model.Message],
        db: AsyncSession
) -> List[schemas.Message]:
    if not db_messages:
        return []

    file_ids_to_hydrate = {
        sub.content for msg in db_messages for sub in msg.sub_messages if sub.type == 'File' and sub.content
    }

    file_info_map = {}
    if file_ids_to_hydrate:
        file_service = FileService(db)
        file_records = await file_service.batch_get_files(list(file_ids_to_hydrate))
        for record in file_records:
            file_info_map[record.id] = file_service.convert_to_schema(record)

    message_responses = []
    for db_message in db_messages:
        message_res = schemas.Message.model_validate(db_message)
        message_res.status = await generation_service._calculate_message_status(db_message)

        for sub_message_res in message_res.sub_messages:
            if sub_message_res.type == 'File' and sub_message_res.content in file_info_map:
                sub_message_res.file_info = file_info_map[sub_message_res.content]

        message_responses.append(message_res)

    return message_responses


@router.get(
    "/chats/{chat_id}/messages",
    response_model=schemas.ChatWithMessages,
    summary="获取单个会话及其消息",
    response_model_exclude_none=True
)
async def read_chat_with_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    await chat_crud.touch_chat(db, chat_id=chat_id)

    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get messages for a folder.")

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None
    _apply_default_model_to_chat_object(db_chat, default_model_id)

    chat_response = schemas.ChatWithMessages.model_validate(db_chat)

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
    chat_response.messages = await _hydrate_and_validate_messages(active_messages, db)

    return chat_response


@router.put(
    "/messages/{message_id}",
    response_model=schemas.UpdateMessageResponse,
    summary="更新消息内容并可选择重新生成",
    response_model_exclude_none=True
)
async def update_message_and_regenerate(
        message_id: str,
        message_update: schemas.MessageUpdate,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    new_message_create = schemas.MessageCreate(
        role=db_message.role,
        sub_messages=message_update.sub_messages,
        parentId=db_message.parentId
    )
    new_user_message = await message_crud.create_message(db, message=new_message_create, chat_id=db_message.chatId)

    if not message_update.resend:
        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
        populated_user_msg = next((m for m in active_msgs if m.id == new_user_message.id), new_user_message)

        hydrated_user_message = (await _hydrate_and_validate_messages([populated_user_msg], db))[0]
        return schemas.UpdateMessageResponse(
            user_message=hydrated_user_message,
            assistant_message=None
        )

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=db_message.chatId, base_message_id=new_user_message.id
    )
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id)

    # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_user_msg = next((m for m in active_msgs if m.id == new_user_message.id), new_user_message)
    populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

    hydrated_messages = await _hydrate_and_validate_messages([populated_user_msg, populated_assistant_msg], db)

    return schemas.UpdateMessageResponse(
        user_message=hydrated_messages[0],
        assistant_message=hydrated_messages[1]
    )


@router.put(
    "/chats/{chat_id}/messages/{message_id}/activate",
    response_model=List[schemas.Message],
    summary="激活指定的消息分支路径",
    response_model_exclude_none=True
)
async def activate_message_branch(chat_id: str, message_id: str, db: AsyncSession = Depends(get_db)):
    success = await message_crud.activate_message_path(db, message_id=message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
    return await _hydrate_and_validate_messages(active_messages, db)


@router.delete(
    "/messages/{message_id}",
    response_model=schemas.Message,
    summary="删除单条消息",
    response_model_exclude_none=True
)
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 修复: 在物理删除前提前完成 Hydrate，防止删除后触发懒加载导致崩溃
    hydrated_messages = await _hydrate_and_validate_messages([db_message], db)

    await message_crud.delete_message(db, message_id=message_id)

    return hydrated_messages[0]


@router.put("/sub-messages/{sub_message_id}", response_model=schemas.SubMessage, summary="更新单个消息分区")
async def update_sub_message(
        sub_message_id: str,
        sub_message_update: schemas.SubMessageUpdate,
        db: AsyncSession = Depends(get_db)
):
    updated_sub_message = await message_crud.update_sub_message(db, sub_message_id, sub_message_update)
    if not updated_sub_message:
        raise HTTPException(status_code=404, detail="SubMessage not found")
    return updated_sub_message


@router.post("/messages/{message_id}/stop", status_code=status.HTTP_202_ACCEPTED, summary="请求停止AI生成")
async def stop_generation(message_id: str, db: AsyncSession = Depends(get_db)):
    await stream_manager.request_cancellation(message_id)
    await stream_manager.mark_task_completed(message_id)

    # 立即释放该会话的生成锁，使前端停止后可以立刻重新生成。
    db_message = await message_crud.get_message(db, message_id=message_id)
    if db_message:
        await stream_manager.release_generation_lock(db_message.chatId)

    return {"message": "Cancellation requested."}


@router.post(
    "/messages/{message_id}/compress-history",
    status_code=status.HTTP_202_ACCEPTED,
    summary="压缩指定消息及之前的所有对话历史"
)
async def compress_history_above_message(
        message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    if db_message.role != schemas.MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="History compression can only be initiated from an assistant's message."
        )

    background_tasks.add_task(
        generation_service.run_zip_history_generation_task,
        chat_id=db_message.chatId,
        target_message_id=message_id
    )
    return {"message": "History compression task has been initiated."}


@router.post(
    "/chats/{chat_id}/prepare-generate",
    response_model=schemas.PrepareGenerateResponse,
    summary="准备并开始生成AI回复",
    response_model_exclude_none=True
)
async def prepare_to_generate(
        chat_id: str,
        request: schemas.GenerateRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        user_message, assistant_placeholder = await generation_service.create_user_message_and_prepare_generation(
            db=db, chat_id=chat_id, request=request
        )
        await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        populated_user_msg = next((m for m in active_msgs if m.id == user_message.id), user_message)
        populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

        hydrated_messages = await _hydrate_and_validate_messages([populated_user_msg, populated_assistant_msg], db)

        return schemas.PrepareGenerateResponse(
            user_message=hydrated_messages[0],
            assistant_message=hydrated_messages[1]
        )
    except Exception:
        await stream_manager.release_generation_lock(chat_id)
        raise


@router.post(
    "/chats/{chat_id}/prepare-regenerate/{from_message_id}",
    response_model=schemas.Message,
    summary="准备并开始重新生成AI回复",
    response_model_exclude_none=True
)
async def prepare_to_regenerate(
        chat_id: str,
        from_message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        assistant_placeholder = await generation_service.prepare_for_regeneration(
            db=db, chat_id=chat_id, base_message_id=from_message_id
        )
        await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

        hydrated_messages = await _hydrate_and_validate_messages([populated_assistant_msg], db)
        return hydrated_messages[0]
    except Exception:
        await stream_manager.release_generation_lock(chat_id)
        raise


@router.post(
    "/messages/{message_id}/retry",
    response_model=schemas.Message,
    summary="重试失败的生成任务（从 LangGraph checkpoint 恢复）",
    response_model_exclude_none=True
)
async def retry_failed_generation(
        message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    if db_message.role != schemas.MessageRole.ASSISTANT:
        raise HTTPException(status_code=400, detail="Retry is only applicable to assistant messages.")

    calculated_status = await generation_service._calculate_message_status(db_message)
    if calculated_status != schemas.MessageStatus.FAILED:
        raise HTTPException(status_code=400, detail="Retry is only applicable to failed messages.")

    if not await stream_manager.try_acquire_generation_lock(db_message.chatId):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        await _start_generation_task(background_tasks, db_message.chatId, message_id, is_retry=True)

        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
        populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

        hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
        response_message = hydrated_messages[0]
        response_message.status = schemas.MessageStatus.GENERATING

        return response_message
    except Exception:
        await stream_manager.release_generation_lock(db_message.chatId)
        raise


@router.post(
    "/chats/{chat_id}/generate-title",
    status_code=status.HTTP_202_ACCEPTED,
    summary="自动生成会话标题"
)
async def generate_chat_title(
        chat_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Title generation is only applicable to chats, not folders.")

    background_tasks.add_task(generation_service.run_title_generation_task, chat_id)
    return {"message": "Title generation has been initiated."}


@router.get(
    "/chats/{chat_id}/stream-response/{assistant_message_id}",
    summary="订阅AI回复的流式输出",
    response_description="一个Server-Sent Events (SSE)流。"
)
async def stream_response(
        chat_id: str,
        assistant_message_id: str,
        db: AsyncSession = Depends(get_db)
):
    return StreamingResponse(
        generation_service.subscribe_to_stream(db, assistant_message_id),
        media_type="text/event-stream"
    )

@router.post(
    "/messages/{message_id}/review-tool",
    response_model=schemas.Message,
    summary="提交工具调用审核决策",
    response_model_exclude_none=True
)
async def review_tool_call(
        message_id: str,
        request: ToolApprovalRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    from backend.schemas.message import ReviewToolContent

    db_sub = await message_crud.get_sub_message(db, request.sub_message_id)
    if not db_sub or db_sub.messageId != message_id or db_sub.type != SubMessageType.REVIEW_TOOL.value:
        raise HTTPException(status_code=404, detail="Review tool request not found.")

    review_content = ReviewToolContent.from_json_string(db_sub.content)
    review_content.decision = request.decision

    await message_crud.update_sub_message(
        db,
        request.sub_message_id,
        schemas.SubMessageUpdate(content=review_content.to_json_string())
    )

    db_message = await message_crud.get_message(db, message_id=message_id)
    pending_review_subs = [
        sub for sub in db_message.sub_messages
        if sub.type == SubMessageType.REVIEW_TOOL.value and sub.status == MessageStatus.PENDING_REVIEW.value
    ]

    all_decided = True
    for sub in pending_review_subs:
        content = ReviewToolContent.from_json_string(sub.content)
        if content.decision is None:
            all_decided = False
            break

    is_resuming = False

    if all_decided and pending_review_subs:
        sub_ids = [sub.id for sub in pending_review_subs]
        affected_rows = await message_crud.batch_update_sub_messages_status_optimistic(
            db, sub_ids, MessageStatus.PENDING_REVIEW, MessageStatus.COMPLETED
        )

        if affected_rows == len(sub_ids):
            await _start_generation_task(background_tasks, db_message.chatId, message_id)
            is_resuming = True

    # 修复: 从活跃路径中重新获取，以装配 sibling 元数据
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING

    return response_message


@router.post(
    "/messages/{message_id}/answer-ask-user",
    response_model=schemas.Message,
    summary="提交 ask_user 问题回答",
    response_model_exclude_none=True
)
async def answer_ask_user(
        message_id: str,
        request: AskUserAnswerRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    from backend.schemas.message import AskUserContent

    db_sub = await message_crud.get_sub_message(db, request.sub_message_id)
    if not db_sub or db_sub.messageId != message_id or db_sub.type != SubMessageType.ASK_USER.value:
        raise HTTPException(status_code=404, detail="AskUser request not found.")

    ask_content = AskUserContent.from_json_string(db_sub.content)
    ask_content.answers = request.answers
    ask_content.ask_status = request.ask_status

    await message_crud.update_sub_message(
        db,
        request.sub_message_id,
        schemas.SubMessageUpdate(content=ask_content.to_json_string())
    )

    db_message = await message_crud.get_message(db, message_id=message_id)
    pending_ask_subs = [
        sub for sub in db_message.sub_messages
        if sub.type == SubMessageType.ASK_USER.value and sub.status == MessageStatus.PENDING_REVIEW.value
    ]

    all_answered = True
    for sub in pending_ask_subs:
        try:
            content = AskUserContent.from_json_string(sub.content)
            if content.answers is None:
                all_answered = False
                break
        except (ValueError, ImportError):
            all_answered = False
            break

    is_resuming = False

    if all_answered and pending_ask_subs:
        sub_ids = [sub.id for sub in pending_ask_subs]
        affected_rows = await message_crud.batch_update_sub_messages_status_optimistic(
            db, sub_ids, MessageStatus.PENDING_REVIEW, MessageStatus.COMPLETED
        )

        if affected_rows == len(sub_ids):
            await _start_generation_task(background_tasks, db_message.chatId, message_id)
            is_resuming = True

    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING

    return response_message
