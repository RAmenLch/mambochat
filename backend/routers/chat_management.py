# backend/routers/chat_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from backend.crud import chat_crud, setting_crud, provider_crud
from backend.services import chat_service
from backend import schemas
from backend.models import chat_model
from backend.database import get_db
from backend.routers.settings import get_global_settings
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS

router = APIRouter()

# --- Helper function for parameter validation ---

# Create a lookup map for efficient access to parameter definitions
_param_definition_map = {param.key: param for param in SUPPORTED_LLM_PARAMETERS}


def _validate_model_parameters(params: Dict[str, Any]):
    """
    Validates a dictionary of model parameters against the central configuration.
    Raises HTTPException for any validation failures.
    """
    for key, value in params.items():
        # These parameters are managed by the system but not defined in the central config
        if key in ["max_context_messages", "stream", "enabled_mcp_ids"]:
            continue

        definition = _param_definition_map.get(key)
        if not definition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parameter '{key}' is not supported by the system."
            )

        # Type validation
        expected_type = {
            "number": (float, int),
            "integer": int,
            "string": str,
            "boolean": bool
        }.get(definition.type)

        if not isinstance(value, expected_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid type for parameter '{key}'. Expected {definition.type}, got {type(value).__name__}."
            )

        # Limit validation
        if definition.limit:
            if definition.type in ["number", "integer"]:
                min_val = definition.limit.get("min")
                max_val = definition.limit.get("max")
                if (min_val is not None and value < min_val) or \
                        (max_val is not None and value > max_val):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Value for '{key}' is out of range. Must be between {min_val} and {max_val}."
                    )
            elif definition.type == "string":
                if value not in definition.limit:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid value for '{key}'. Must be one of: {', '.join(definition.limit)}"
                    )


def _apply_default_model_to_chat_object(chat: chat_model.Chat, default_model_id: Optional[str]):
    """If a chat session does not have a model ID, assign the global default model ID to it."""
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
    Creates a new session (itemType='chat') or folder (itemType='folder').
    - If no model is specified for a session, the global default model is used.
    - If no model parameters are specified, default parameters are applied based on system configuration and global settings.
    - All provided model parameters are validated against the system configuration.
    """
    if chat.itemType == 'chat':
        if not chat.aiModelId:
            default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
            if default_model_setting and default_model_setting.value:
                chat.aiModelId = default_model_setting.value

        if chat.aiModelId:
            db_model = await provider_crud.get_model(db, model_id=chat.aiModelId)
            if not db_model:
                raise HTTPException(status_code=404, detail=f"AI model ID {chat.aiModelId} not found")

        if chat.modelParameters is None:
            global_settings = await get_global_settings(db)
            default_params = {
                "max_context_messages": global_settings.default_max_context_messages,
                "stream": global_settings.default_stream,
            }
            # Apply default activated parameters from central config
            for param_def in SUPPORTED_LLM_PARAMETERS:
                if param_def.default_activate:
                    default_params[param_def.key] = param_def.default_value

            # Override with global settings if they are explicitly set
            if global_settings.default_temperature is not None:
                default_params["temperature"] = global_settings.default_temperature
            if global_settings.default_top_p is not None:
                default_params["top_p"] = global_settings.default_top_p

            chat.modelParameters = default_params
        else:
            # Validate user-provided parameters
            _validate_model_parameters(chat.modelParameters)

    return await chat_crud.create_chat(db=db, chat=chat)


@router.post(
    "/chats/reorder",
    status_code=status.HTTP_200_OK,
    summary="批量更新会话和文件夹排序"
)
async def reorder_chats(updates: List[schemas.ChatReorderItem], db: AsyncSession = Depends(get_db)):
    """
    Receives a list of items with ID, new parent ID, and new sort order to perform a batch update.
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
    Updates the configuration of a specific item, such as changing the model, name, or parent folder.
    All provided model parameters are validated against the system configuration.
    """

    if chat_update.aiModelId:
        db_model = await provider_crud.get_model(db, model_id=chat_update.aiModelId)
        if not db_model:
            raise HTTPException(status_code=404, detail=f"AI model ID {chat_update.aiModelId} not found")

    if chat_update.modelParameters is not None:
        _validate_model_parameters(chat_update.modelParameters)

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
    Creates a new session with the same configuration and message history as the given session ID.
    """
    new_chat = await chat_service.duplicate_chat_with_messages(db, chat_id=chat_id)
    if not new_chat:
        raise HTTPException(status_code=404, detail="Source chat not found or is a folder")
    return new_chat
