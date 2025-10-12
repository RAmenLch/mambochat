# backend/routers/chats.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from fastapi.responses import StreamingResponse

from ..services import llm_service
from .. import crud, schemas
from ..database import get_db

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

    # 为列表中模型ID为空的会话应用全局默认模型回退
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

    # 如果会话的模型被删除，则在返回数据时回退至全局默认模型
    if db_chat.itemType == 'chat' and not db_chat.aiModelId:
        default_model_setting = await crud.get_setting(db, key="default_model_id")
        if default_model_setting and default_model_setting.value:
            db_chat.aiModelId = default_model_setting.value

    return db_chat


@router.get("/chats/{chat_id}/messages", response_model=schemas.ChatWithMessages, summary="获取单个会话及其消息")
async def read_chat_with_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    # 当用户获取消息时，更新会话的“最后打开时间”
    await crud.touch_chat(db, chat_id=chat_id)

    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get messages for a folder.")

    # 如果会话的模型被删除，则在返回数据时回退至全局默认模型
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
    根据给定的会话ID，创建一个配置相同的新会话。
    """
    new_chat = await crud.duplicate_chat(db, chat_id=chat_id)
    if not new_chat:
        raise HTTPException(status_code=404, detail="Source chat not found or is a folder")
    return new_chat


# --- Message and Generation Routes ---

@router.post(
    "/chats/{chat_id}/messages",
    response_model=schemas.Message,
    status_code=status.HTTP_201_CREATED,
    summary="在会话中创建新消息"
)
async def create_message_for_chat(
        chat_id: str, message: schemas.MessageCreate, db: AsyncSession = Depends(get_db)
):
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot add messages to a folder.")
    return await crud.create_message(db=db, message=message, chat_id=chat_id)


@router.put("/messages/{message_id}", summary="更新消息内容 (并可选择重新生成)")
async def update_message_content(
        message_id: str,
        message_update: schemas.MessageUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新指定消息的内容。
    如果 `resend` 为 true（仅限用户消息），则更新内容后，删除后续所有消息并准备重新生成AI回答。
    此端点将返回一个空的 assistant 消息占位符，客户端需使用其ID调用流式端点。
    """
    db_message = await crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    updated_message = await crud.update_message(db, message_id=message_id, message_update=message_update)

    if not message_update.resend:
        return updated_message

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    # 准备重新生成
    return await llm_service.prepare_for_generation(
        db=db,
        chat_id=db_message.chatId,
        base_message_id=message_id,
        save_user_message=False
    )


@router.delete("/messages/{message_id}", response_model=schemas.Message, summary="删除单条消息")
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await crud.delete_message(db, message_id=message_id)
    if db_message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return db_message


# --- Two-Step Generation Endpoints ---

@router.post(
    "/chats/{chat_id}/prepare-generate",
    response_model=schemas.Message,
    summary="第一步：准备生成AI回复"
)
async def prepare_to_generate(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    接收用户新消息，保存它，然后创建一个空的 assistant 消息作为占位符，并将其返回。
    客户端下一步应使用返回消息的ID来调用流式端点。
    """
    return await llm_service.prepare_for_generation(
        db=db,
        chat_id=chat_id,
        user_content=request.content,
        save_user_message=True
    )


@router.post(
    "/chats/{chat_id}/prepare-regenerate/{from_message_id}",
    response_model=schemas.Message,
    summary="第一步：准备重新生成AI回复"
)
async def prepare_to_regenerate(
        chat_id: str,
        from_message_id: str,
        db: AsyncSession = Depends(get_db)
):
    """
    根据指定消息，删除其后的对话历史，然后创建一个空的 assistant 消息作为占位符，并将其返回。
    客户端下一步应使用返回消息的ID来调用流式端点。
    """
    return await llm_service.prepare_for_generation(
        db=db,
        chat_id=chat_id,
        base_message_id=from_message_id,
        save_user_message=False
    )


@router.get(
    "/chats/{chat_id}/stream-response/{assistant_message_id}",
    summary="第二步：流式获取AI回复",
    response_description="一个包含新AI回复文本块的Server-Sent Events (SSE)流"
)
async def stream_response(
        chat_id: str,
        assistant_message_id: str,
        db: AsyncSession = Depends(get_db)
):
    """
    根据第一步创建的 assistant 消息占位符的ID，流式生成并返回AI的完整响应。
    """
    return StreamingResponse(
        llm_service.stream_chat_response(db, chat_id, assistant_message_id),
        media_type="text/event-stream"
    )


# --- Non-Stream Endpoints (Legacy or for specific use cases) ---

@router.post(
    "/chats/{chat_id}/generate-non-stream",
    response_model=schemas.Message,
    summary="生成AI回复 (非流式)",
    response_description="一个包含完整AI回复的消息JSON对象"
)
async def generate_response_non_stream(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession = Depends(get_db)
):
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot generate response for a folder.")
    assistant_message = await llm_service.generate_chat_response_non_stream(chat_id, request, db)
    return assistant_message


@router.post(
    "/chats/{chat_id}/regenerate-non-stream",
    response_model=schemas.Message,
    summary="重新生成AI回复 (非流式)",
    response_description="一个包含新AI回复的消息JSON对象"
)
async def regenerate_response_non_stream(
        chat_id: str,
        request: schemas.GenerateRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    删除最后一条AI的回复，并根据相同的用户输入重新生成一次（非流式）。
    """
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot regenerate response for a folder.")

    await crud.delete_last_assistant_message(db, chat_id=chat_id)

    assistant_message = await llm_service.generate_chat_response_non_stream(
        chat_id,
        request,
        db,
        save_user_message=False
    )
    return assistant_message
