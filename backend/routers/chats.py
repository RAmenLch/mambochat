# backend/routers/chats.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi.responses import StreamingResponse

from ..services import llm_service
from .. import crud, schemas
from ..database import get_db, AsyncSessionLocal

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
    """
    if chat.itemType == 'chat' and chat.aiModelId:
        db_model = await crud.get_model(db, model_id=chat.aiModelId)
        if not db_model:
            raise HTTPException(status_code=404, detail=f"AI Model with id {chat.aiModelId} not found")
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
    return chats


@router.get("/chats/{chat_id}", response_model=schemas.Chat, summary="获取单个会话或文件夹的配置")
async def read_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return db_chat


@router.get("/chats/{chat_id}/messages", response_model=schemas.ChatWithMessages, summary="获取单个会话及其消息")
async def read_chat_with_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    # 当用户获取消息时，更新会话的“最后打开时间”
    await crud.touch_chat(db, chat_id=chat_id)

    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 确保只为“会话”类型的项目获取消息
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get messages for a folder.")

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
            raise HTTPException(status_code=404, detail=f"AI Model with id {chat_update.aiModelId} not found")

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


@router.post(
    "/chats/{chat_id}/generate",
    summary="生成AI回复 (流式)",
    response_description="一个包含AI回复文本块的Server-Sent Events (SSE)流"
)
async def generate_response(
        chat_id: str,
        request: schemas.GenerateRequest,
):
    """
    接收用户消息，调用后端LLM服务，并以流式方式返回AI的响应。
    """
    async with AsyncSessionLocal() as db:
        db_chat = await crud.get_chat(db, chat_id=chat_id)
        if not db_chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        if db_chat.itemType != 'chat':
            raise HTTPException(status_code=400, detail="Cannot generate response for a folder.")

    return StreamingResponse(
        llm_service.generate_chat_response(chat_id, request),
        media_type="text/event-stream"
    )


@router.post(
    "/chats/{chat_id}/regenerate",
    summary="重新生成AI回复 (流式)",
    response_description="一个包含新AI回复文本块的Server-Sent Events (SSE)流"
)
async def regenerate_response(
        chat_id: str,
        request: schemas.GenerateRequest,
):
    """
    删除最后一条AI的回复，并根据相同的用户输入重新生成一次。
    """
    async with AsyncSessionLocal() as db:
        db_chat = await crud.get_chat(db, chat_id=chat_id)
        if not db_chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        if db_chat.itemType != 'chat':
            raise HTTPException(status_code=400, detail="Cannot regenerate response for a folder.")

        await crud.delete_last_assistant_message(db, chat_id=chat_id)

    return StreamingResponse(
        llm_service.generate_chat_response(chat_id, request, save_user_message=False),
        media_type="text/event-stream"
    )


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
