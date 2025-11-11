# backend/routers/chat_interaction.py

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
import json
import logging

from ..services import generation_service
from ..services.stream_manager_service import stream_manager
from ..crud import chat_crud, message_crud, setting_crud
from .. import schemas
from ..database import get_db
from .chat_management import _apply_default_model_to_chat_object

router = APIRouter()


async def _start_generation_task(
        background_tasks: BackgroundTasks,
        chat_id: str,
        assistant_message_id: str
):
    """启动后台生成任务。"""
    background_tasks.add_task(generation_service._run_managed_generation_task, chat_id, assistant_message_id)


@router.get("/chats/{chat_id}/messages", response_model=schemas.ChatWithMessages, summary="获取单个会话及其消息")
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

    # 手动构建响应模型以注入动态计算的 status 字段
    chat_response = schemas.ChatWithMessages.model_validate(db_chat)

    # 为每条消息计算并设置其状态
    message_responses = []
    for db_message in db_chat.messages:
        message_res = schemas.Message.model_validate(db_message)
        message_res.status = await generation_service._calculate_message_status(db_message)
        message_responses.append(message_res)

    chat_response.messages = message_responses

    return chat_response


@router.put("/messages/{message_id}", response_model=schemas.Message, summary="更新消息内容并可选择重新生成")
async def update_message_and_regenerate(
        message_id: str,
        message_update: schemas.MessageUpdate,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    """
    替换指定消息的全部内容分区。
    如果 `resend` 为 true（仅限用户消息），则删除后续消息并启动后台任务重新生成AI回答。
    """
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    updated_message = await message_crud.update_message(db, message_id=message_id, message_update=message_update)
    if not updated_message:
        raise HTTPException(status_code=500, detail="Failed to update message")

    if not message_update.resend:
        response_message = schemas.Message.model_validate(updated_message)
        response_message.status = await generation_service._calculate_message_status(updated_message)
        return response_message

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=db_message.chatId, base_message_id=message_id
    )
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id)

    response_placeholder = schemas.Message.model_validate(assistant_placeholder)
    response_placeholder.status = schemas.MessageStatus.GENERATING
    return response_placeholder


@router.delete("/messages/{message_id}", response_model=schemas.Message, summary="删除单条消息")
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await message_crud.delete_message(db, message_id=message_id)
    if db_message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return db_message


@router.put("/sub-messages/{sub_message_id}", response_model=schemas.SubMessage, summary="更新单个消息分区")
async def update_sub_message(
        sub_message_id: str,
        sub_message_update: schemas.SubMessageUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新单个消息分区的内容、配置或状态。
    此操作不触发AI重新生成。
    """
    updated_sub_message = await message_crud.update_sub_message(db, sub_message_id, sub_message_update)
    if not updated_sub_message:
        raise HTTPException(status_code=404, detail="SubMessage not found")
    return updated_sub_message


@router.post("/messages/{message_id}/stop", status_code=status.HTTP_202_ACCEPTED, summary="请求停止AI生成")
async def stop_generation(message_id: str):
    """
    向后台发送一个请求，以优雅地停止与指定消息ID关联的生成任务。
    """
    await stream_manager.request_cancellation(message_id)
    return {"message": "Cancellation requested."}


@router.post(
    "/chats/{chat_id}/prepare-generate",
    response_model=schemas.PrepareGenerateResponse,
    summary="准备并开始生成AI回复"
)
async def prepare_to_generate(
        chat_id: str,
        request: schemas.GenerateRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    """
    接收用户新消息，保存它，创建一个空的 assistant 消息占位符并返回两者。
    同时，根据会话设置在后台启动一个生成任务。
    """
    user_message, assistant_placeholder = await generation_service.create_user_message_and_prepare_generation(
        db=db, chat_id=chat_id, user_sub_messages=request.sub_messages
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

    user_message_response = schemas.Message.model_validate(user_message)
    user_message_response.status = schemas.MessageStatus.COMPLETED

    assistant_placeholder_response = schemas.Message.model_validate(assistant_placeholder)
    assistant_placeholder_response.status = schemas.MessageStatus.GENERATING

    return schemas.PrepareGenerateResponse(
        user_message=user_message_response,
        assistant_message=assistant_placeholder_response
    )


@router.post(
    "/chats/{chat_id}/prepare-regenerate/{from_message_id}",
    response_model=schemas.Message,
    summary="准备并开始重新生成AI回复"
)
async def prepare_to_regenerate(
        chat_id: str,
        from_message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    """
    根据指定消息删除后续历史，创建占位符并返回。
    同时，根据会话设置在后台启动一个重新生成任务。
    """
    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=chat_id, base_message_id=from_message_id
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

    response_placeholder = schemas.Message.model_validate(assistant_placeholder)
    response_placeholder.status = schemas.MessageStatus.GENERATING
    return response_placeholder


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
    """
    为指定的会话异步触发一个后台任务，以根据其内容自动生成标题。
    """
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
    """
    客户端通过此端点订阅指定 assistant 消息的生成进度。
    """
    return StreamingResponse(
        generation_service.subscribe_to_stream(db, assistant_message_id),
        media_type="text/event-stream"
    )
