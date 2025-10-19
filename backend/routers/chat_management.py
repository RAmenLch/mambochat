# backend/routers/chat_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from ..crud import chat_crud, setting_crud, provider_crud
from ..services import chat_service
from .. import schemas
from ..models import chat_model
from ..database import get_db
from .settings import get_global_settings

router = APIRouter()


def _apply_default_model_to_chat_object(chat: chat_model.Chat, default_model_id: Optional[str]):
    """如果会话本身没有模型ID，则将全局默认模型ID赋值给它。"""
    if chat.itemType == 'chat' and not chat.aiModelId and default_model_id:
        chat.aiModelId = default_model_id


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
            default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
            if default_model_setting and default_model_setting.value:
                chat.aiModelId = default_model_setting.value

        if chat.aiModelId:
            db_model = await provider_crud.get_model(db, model_id=chat.aiModelId)
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

    return await chat_crud.create_chat(db=db, chat=chat)


@router.post(
    "/chats/reorder",
    status_code=status.HTTP_200_OK,
    summary="批量更新会话和文件夹排序"
)
async def reorder_chats(updates: List[schemas.ChatReorderItem], db: AsyncSession = Depends(get_db)):
    """
    接收一个包含ID、新父ID和新排序顺序的列表，以批量更新项目。
    """
    await chat_crud.batch_update_chats_order(db, updates=updates)
    return {"message": "Reorder successful"}


@router.get("/chats/", response_model=List[schemas.Chat], summary="获取会话和文件夹列表")
async def read_chats(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    chats = await chat_crud.get_chats(db, skip=skip, limit=limit)

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None

    for chat in chats:
        _apply_default_model_to_chat_object(chat, default_model_id)

    return chats


@router.get("/chats/{chat_id}", response_model=schemas.Chat, summary="获取单个会话或文件夹的配置")
async def read_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None
    _apply_default_model_to_chat_object(db_chat, default_model_id)

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
        db_model = await provider_crud.get_model(db, model_id=chat_update.aiModelId)
        if not db_model:
            raise HTTPException(status_code=404, detail=f"AI 模型ID {chat_update.aiModelId} 未找到")

    updated_chat = await chat_crud.update_chat(db, chat_id=chat_id, chat_update=chat_update)

    if updated_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return updated_chat


@router.delete("/chats/{chat_id}", response_model=schemas.Chat, summary="删除会话或文件夹")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await chat_crud.delete_chat(db, chat_id=chat_id)
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
    new_chat = await chat_service.duplicate_chat_with_messages(db, chat_id=chat_id)
    if not new_chat:
        raise HTTPException(status_code=404, detail="Source chat not found or is a folder")
    return new_chat

