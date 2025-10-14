# backend/routers/chats.py

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi.responses import StreamingResponse
import json

from ..services import llm_service, stream_manager
from .. import crud, schemas
from ..database import get_db
from .settings import get_global_settings # 导入以复用逻辑

router = APIRouter()


# --- Chat and Folder Routes ---

@router.post(
    "/chats/",
    response_model=schemas.Chat,
    status_code=status.HTTP_201_CREATED,
    summary="创建新会话或文件夹"
)
async def create_chat(chat: schemas.ChatCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的会话 (itemType='chat') 或文件夹 (itemType='folder')。
    如果创建会话时未指定模型，将尝试使用全局默认模型。
    如果创建会话时未指定模型参数，将自动应用全局默认参数。
    """
    if chat.itemType == 'chat':
        if not chat.aiModelId:
            default_model_setting = await crud.get_setting(db, key="default_model_id")
            if default_model_setting and default_model_setting.value:
                chat.aiModelId = default_model_setting.value

        if chat.aiModelId:
            db_model = await crud.get_model(db, model_id=chat.aiModelId)
            if not db_model:
                raise HTTPException(status_code=404, detail=f"AI 模型ID {chat.aiModelId} 未找到")

        if chat.modelParameters is None:
            global_settings = await get_global_settings(db)
            chat.modelParameters = {
                "max_context_messages": global_settings.default_max_context_messages,
                "temperature": global_settings.default_temperature,
                "top_p": global_settings.default_top_p,
                "stream": global_settings.default_stream,
            }

    return await crud.create_chat(db=db, chat=chat)


@router.post(
    "/chats/reorder",
    status_code=status.HTTP_200_OK,
    summary="批量更新会话和文件夹排序"
)
async def reorder_chats(updates: List[schemas.ChatReorderItem], db: AsyncSession = Depends(get_db)):
    """
    接收一个包含ID、新父ID和新排序顺序的列表，以批量更新项目。
    """
    await crud.batch_update_chats_order(db, updates=updates)
    return {"message": "Reorder successful"}


@router.get("/chats/", response_model=List[schemas.Chat], summary="获取会话和文件夹列表")
async def read_chats(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    chats = await crud.get_chats(db, skip=skip, limit=limit)

    default_model_setting = await crud.get_setting(db, key="default_model_id")
    if default_model_setting and default_model_setting.value:
        default_model_id = default_model_setting.value
        for chat in chats:
            if chat.itemType == 'chat' and not chat.aiModelId:
                chat.aiModelId = default_model_id

    return chats


@router.get("/chats/{chat_id}", response_model=schemas.Chat, summary="获取单个会话或文件夹的配置")
async def read_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")

    if db_chat.itemType == 'chat' and not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value

    return db_chat


@router.get("/chats/{chat_id}/messages", response_model=schemas.ChatWithMessages, summary="获取单个会话及其消息")
async def read_chat_with_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    await crud.touch_chat(db, chat_id=chat_id)

    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get messages for a folder.")

    if not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value

    return db_chat


@router.put(
    "/chats/{chat_id}",
    response_model=schemas.Chat,
    summary="更新会话或文件夹配置"
)
async def update_chat_settings(
        chat_id: str,
        chat_update: schemas.ChatUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新指定项目的配置，例如更换模型、修改名称、移动到不同文件夹等。
    """
    if chat_update.aiModelId:
        db_model = await crud.get_model(db, model_id=chat_update.aiModelId)
        if not db_model:
            raise HTTPException(status_code=404, detail=f"AI 模型ID {chat_update.aiModelId} 未找到")

    updated_chat = await crud.update_chat(db, chat_id=chat_id, chat_update=chat_update)

    if updated_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return updated_chat


@router.delete("/chats/{chat_id}", response_model=schemas.Chat, summary="删除会话或文件夹")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await crud.delete_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return db_chat


@router.post(
    "/chats/{chat_id}/duplicate",
    response_model=schemas.Chat,
    status_code=status.HTTP_201_CREATED,
    summary="复制会话"
)
async def duplicate_chat_endpoint(chat_id: str, db: AsyncSession = Depends(get_db)):
    """
    根据给定的会话ID，创建一个配置和消息历史都相同的新会话。
    """
    new_chat = await crud.duplicate_chat(db, chat_id=chat_id)
    if not new_chat:
        raise HTTPException(status_code=404, detail="Source chat not found or is a folder")
    return new_chat


# --- Message and Generation Routes ---

async def _start_generation_task(
    background_tasks: BackgroundTasks,
    chat_id: str,
    assistant_message_id: str,
    db: AsyncSession
):
    """根据会话设置决定启动流式或非流式后台任务。"""
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    use_stream = True
    if db_chat and db_chat.modelParameters:
        try:
            params = json.loads(db_chat.modelParameters)
            if params.get('stream') is False:
                use_stream = False
        except (json.JSONDecodeError, TypeError):
            pass

    if use_stream:
        background_tasks.add_task(llm_service.run_generation_task_stream, chat_id, assistant_message_id)
    else:
        background_tasks.add_task(llm_service.run_generation_task_non_stream, chat_id, assistant_message_id)


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
    db_message = await crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    updated_message = await crud.update_message(db, message_id=message_id, message_update=message_update)
    if not updated_message:
        raise HTTPException(status_code=500, detail="Failed to update message")

    if not message_update.resend:
        return updated_message

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    assistant_placeholder = await llm_service.prepare_for_generation(
        db=db, chat_id=db_message.chatId, base_message_id=message_id, save_user_message=False
    )
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id, db)
    return assistant_placeholder


@router.delete("/messages/{message_id}", response_model=schemas.Message, summary="删除单条消息")
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await crud.delete_message(db, message_id=message_id)
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
    updated_sub_message = await crud.update_sub_message(db, sub_message_id, sub_message_update)
    if not updated_sub_message:
        raise HTTPException(status_code=404, detail="SubMessage not found")
    return updated_sub_message


@router.post("/messages/{message_id}/stop", status_code=status.HTTP_202_ACCEPTED, summary="请求停止AI生成")
async def stop_generation(message_id: str):
    """
    向后台发送一个请求，以优雅地停止与指定消息ID关联的生成任务。
    """
    await stream_manager.stream_manager.request_cancellation(message_id)
    return {"message": "Cancellation requested."}


# --- Generation Endpoints ---

@router.post(
    "/chats/{chat_id}/prepare-generate",
    response_model=schemas.Message,
    summary="准备并开始生成AI回复"
)
async def prepare_to_generate(
        chat_id: str,
        request: schemas.GenerateRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    """
    接收用户新消息（可能包含多个分区），保存它，创建一个空的 assistant 消息占位符并返回。
    同时，根据会话设置在后台启动一个流式或非流式生成任务。
    """
    assistant_placeholder = await llm_service.prepare_for_generation(
        db=db, chat_id=chat_id, user_sub_messages=request.sub_messages, save_user_message=True
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id, db)
    return assistant_placeholder


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
    同时，根据会话设置在后台启动一个流式或非流式重新生成任务。
    """
    assistant_placeholder = await llm_service.prepare_for_generation(
        db=db, chat_id=chat_id, base_message_id=from_message_id, save_user_message=False
    )
    await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id, db)
    return assistant_placeholder


@router.get(
    "/chats/{chat_id}/stream-response/{assistant_message_id}",
    summary="订阅AI回复的流式输出",
    response_description="一个Server-Sent Events (SSE)流。首先会发送历史内容，然后是实时内容。"
)
async def stream_response(
        chat_id: str,
        assistant_message_id: str,
        db: AsyncSession = Depends(get_db)
):
    """
    客户端通过此端点订阅指定 assistant 消息的生成进度。
    此连接可以随时中断和重连，都会无缝地从上次中断的地方继续。
    """
    return StreamingResponse(
        llm_service.subscribe_to_stream(db, assistant_message_id),
        media_type="text/event-stream"
    )
