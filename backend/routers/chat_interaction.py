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

router = APIRouter()


async def _start_generation_task(
        background_tasks: BackgroundTasks,
        chat_id: str,
        assistant_message_id: str
):
    """启动后台生成任务。"""
    background_tasks.add_task(generation_service._run_managed_generation_task, chat_id, assistant_message_id)


async def _hydrate_and_validate_messages(
        db_messages: List[chat_model.Message],
        db: AsyncSession
) -> List[schemas.Message]:
    """
    一个集中的辅助函数，用于将数据库Message对象转换为包含完整文件信息和动态状态的前端schema对象。
    """
    if not db_messages:
        return []

    # 1. 收集所有文件类型的 SubMessage 的 file_id
    file_ids_to_hydrate = {
        sub.content for msg in db_messages for sub in msg.sub_messages if sub.type == 'File' and sub.content
    }

    # 2. 批量查询文件信息并创建查找表
    file_info_map = {}
    if file_ids_to_hydrate:
        file_service = FileService(db)
        file_records = await file_service.batch_get_files(list(file_ids_to_hydrate))
        for record in file_records:
            file_info_map[record.id] = schemas.File(
                id=record.id,
                filename=record.filename,
                mime_type=record.mime_type,
                size=record.size,
                created_at=record.created_at,
                url=file_service.get_url(record.storage_path)
            )

    # 3. 构建包含状态和文件信息的响应对象列表
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
    chat_response.messages = await _hydrate_and_validate_messages(db_chat.messages, db)

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

    updated_user_message = await message_crud.update_message(db, message_id=message_id, message_update=message_update)
    if not updated_user_message:
        raise HTTPException(status_code=500, detail="Failed to update message")

    if not message_update.resend:
        hydrated_user_message = (await _hydrate_and_validate_messages([updated_user_message], db))[0]
        return schemas.UpdateMessageResponse(
            user_message=hydrated_user_message,
            assistant_message=None
        )

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=db_message.chatId, base_message_id=message_id
    )
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id)

    hydrated_messages = await _hydrate_and_validate_messages([updated_user_message, assistant_placeholder], db)

    return schemas.UpdateMessageResponse(
        user_message=hydrated_messages[0],
        assistant_message=hydrated_messages[1]
    )


@router.delete(
    "/messages/{message_id}",
    response_model=schemas.Message,
    summary="删除单条消息",
    response_model_exclude_none=True
)
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await message_crud.delete_message(db, message_id=message_id)
    if db_message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    hydrated_messages = await _hydrate_and_validate_messages([db_message], db)
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
async def stop_generation(message_id: str):
    await stream_manager.request_cancellation(message_id)
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
    """
    为指定消息（及其之前）的所有对话历史启动一个后台压缩任务。
    只能对助手的消息进行此操作。
    """
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
    user_message, assistant_placeholder = await generation_service.create_user_message_and_prepare_generation(
        db=db, chat_id=chat_id, request=request
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

    hydrated_messages = await _hydrate_and_validate_messages([user_message, assistant_placeholder], db)

    return schemas.PrepareGenerateResponse(
        user_message=hydrated_messages[0],
        assistant_message=hydrated_messages[1]
    )


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
    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=chat_id, base_message_id=from_message_id
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

    hydrated_messages = await _hydrate_and_validate_messages([assistant_placeholder], db)
    return hydrated_messages[0]


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
