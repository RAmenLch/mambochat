# backend/routers/chats.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi.responses import StreamingResponse
from ..services import llm_service

from .. import crud, schemas
from ..database import get_db

router = APIRouter()

# --- Chat Routes ---

@router.post(
    "/chats/",
    response_model=schemas.Chat,
    status_code=status.HTTP_201_CREATED,
    summary="创建新会话"
)
async def create_chat(chat: schemas.ChatCreate, db: AsyncSession = Depends(get_db)):
    if chat.aiModelId:
        db_model = await crud.get_model(db, model_id=chat.aiModelId)
        if not db_model:
            raise HTTPException(status_code=404, detail=f"AI Model with id {chat.aiModelId} not found")
    return await crud.create_chat(db=db, chat=chat)


@router.get("/chats/", response_model=List[schemas.Chat], summary="获取会话列表")
async def read_chats(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    chats = await crud.get_chats(db, skip=skip, limit=limit)
    return chats


@router.get("/chats/{chat_id}", response_model=schemas.ChatWithMessages, summary="获取单个会话及其消息")
async def read_chat_with_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return db_chat


@router.delete("/chats/{chat_id}", response_model=schemas.Chat, summary="删除会话")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await crud.delete_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return db_chat


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
    return await crud.create_message(db=db, message=message, chat_id=chat_id)


@router.post(
    "/chats/{chat_id}/generate",
    summary="生成AI回复 (流式)",
    response_description="一个包含AI回复文本块的Server-Sent Events (SSE)流"
)
async def generate_response(
    chat_id: str,
    request: schemas.GenerateRequest,
    # 【修复1】: 移除 db: AsyncSession = Depends(get_db)，解决生命周期冲突
):
    """
    接收用户消息，调用后端LLM服务，并以流式方式返回AI的响应。
    """
    # 【修复2】: 不再需要预先检查 chat_id，service 层会自己处理
    return StreamingResponse(
        llm_service.generate_chat_response(chat_id, request), # 【修复3】: 不再传递 db
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
    # (非流式接口保持不变，其生命周期管理是正确的)
    db_chat = await crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    assistant_message = await llm_service.generate_chat_response_non_stream(chat_id, request, db)
    return assistant_message
