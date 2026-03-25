# backend/routers/chat_management.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from backend.crud import chat_crud, setting_crud, provider_crud, resource_crud, agent_crud
from backend.services import chat_service
from backend.services.resource_service import validate_mounted_resources
from backend import schemas
from backend.models import chat_model
from backend.database import get_db
from backend.routers.settings import get_global_settings
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS
from backend.schemas.enums import ResourceItemType, ResourceType

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
        if key in ["max_context_messages", "stream", "enable_suggest"]:
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
        if chat.agentId:
            db_agent = await agent_crud.get_agent(db, agent_id=chat.agentId)
            if not db_agent:
                raise HTTPException(status_code=404, detail=f"Agent ID {chat.agentId} not found")

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
                "enable_suggest": global_settings.default_enable_suggest,
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

        # 验证资源挂载列表
        if chat.resource_prompt_list is not None:
            await validate_mounted_resources(db, chat.resource_prompt_list)

    return await chat_crud.create_chat(db=db, chat=chat)


@router.post(
    "/chats/reorder",
    status_code=status.HTTP_200_OK,
    summary="批量更新会话和文件夹排序 (Deprecated)"
)
async def reorder_chats(updates: List[schemas.ChatReorderItem], db: AsyncSession = Depends(get_db)):
    """
    Receives a list of items with ID, new parent ID, and new sort order to perform a batch update.
    Note: This endpoint is deprecated in favor of /chats/move.
    """
    await chat_crud.batch_update_chats_order(db, updates=updates)
    return {"message": "Reorder successful"}


@router.post(
    "/chats/move",
    status_code=status.HTTP_200_OK,
    summary="移动会话或文件夹"
)
async def move_chats(move_request: schemas.ChatMoveRequest, db: AsyncSession = Depends(get_db)):
    """
    移动会话或文件夹到指定位置（Inside, Before, After）。
    """
    success = await chat_crud.move_chats(db, move_request=move_request)
    if not success:
        raise HTTPException(status_code=400, detail="Move operation failed")
    return {"message": "Move successful"}


@router.get("/chats/", response_model=List[schemas.Chat], summary="获取会话和文件夹列表")
async def read_chats(skip: int = 0, limit: int = 1000, db: AsyncSession = Depends(get_db)):
    chats = await chat_crud.get_chats(db, skip=skip, limit=limit)

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None

    for chat in chats:
        _apply_default_model_to_chat_object(chat, default_model_id)

    return chats


@router.get(
    "/chats/children",
    response_model=List[schemas.Chat],
    summary="批量获取子会话和文件夹"
)
async def read_chat_children(
        parentIds: List[str] = Query(..., description="父节点ID列表，'root'代表根目录"),
        db: AsyncSession = Depends(get_db)
):
    """
    根据父节点ID列表并行加载子节点内容。
    """
    chats = await chat_crud.get_chats_by_parent_ids(db, parent_ids=parentIds)

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None

    for chat in chats:
        _apply_default_model_to_chat_object(chat, default_model_id)

    return chats


@router.post(
    "/chats/search",
    response_model=schemas.SearchResponse,
    summary="全局搜索会话和消息"
)
async def search_chats(request: schemas.SearchRequest, db: AsyncSession = Depends(get_db)):
    """
    在会话标题、系统提示词和消息内容中进行全局搜索。
    支持模糊查询和正则查询，支持指定目录范围。
    """
    skip = (request.page_num - 1) * request.page_size

    rows, total = await chat_crud.search_chats_and_messages(
        db,
        keyword=request.keyword,
        root_id=request.root_id,
        enable_regex=request.enable_regex,
        skip=skip,
        limit=request.page_size
    )

    if not rows:
        return schemas.SearchResponse(total=0, items=[])

    # 提取所有涉及的 chat_id，批量构建路径
    chat_ids = list({row.chat_id for row in rows})
    path_map = await chat_service.build_chat_paths(db, chat_ids)

    items = []
    for row in rows:
        # 截取上下文
        context = chat_service.extract_context_snippet(
            content=row.raw_content,
            keyword=request.keyword,
            enable_regex=request.enable_regex
        )

        item = schemas.SearchResultItem(
            chat_id=row.chat_id,
            chat_name=row.chat_name,
            chat_path=path_map.get(row.chat_id, ""),
            match_type=row.match_type,
            context_text=context,
            sub_message_id=row.sub_message_id,
            created_at=row.created_at
        )
        items.append(item)

    return schemas.SearchResponse(total=total, items=items)


@router.get("/chats/{chat_id}", response_model=schemas.Chat, summary="获取单个会话或文件夹的配置")
async def read_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Item not found")

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None
    _apply_default_model_to_chat_object(db_chat, default_model_id)

    return db_chat


@router.get("/chats/{chat_id}/lineage", response_model=List[schemas.Chat], summary="获取会话链路")
async def get_chat_lineage(chat_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取指定会话的所有祖先节点（包括自身），用于展开目录树。
    """
    ancestors = await chat_crud.get_batch_chat_ancestors(db, chat_ids=[chat_id])
    return ancestors


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

    if chat_update.agentId:
        db_agent = await agent_crud.get_agent(db, agent_id=chat_update.agentId)
        if not db_agent:
            raise HTTPException(status_code=404, detail=f"Agent ID {chat_update.agentId} not found")

    if chat_update.modelParameters is not None:
        _validate_model_parameters(chat_update.modelParameters)

    # 验证资源挂载列表
    if chat_update.resource_prompt_list is not None:
        await validate_mounted_resources(db, chat_update.resource_prompt_list)

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
    "/{chat_id}/duplicate",
    response_model=schemas.Chat,  # 响应模型根据你实际情况(Chat或ChatWithMessages)决定
    summary="复制指定会话"
)
async def duplicate_chat_endpoint(
    chat_id: str,
    payload: schemas.ChatDuplicateRequest = Body(default_factory=schemas.ChatDuplicateRequest),
    db: AsyncSession = Depends(get_db)
):
    """
    复制会话。如果不传参数，则全量复制；如果传入 up_to_message_id，则触发截断复制。
    """
    new_chat = await chat_service.duplicate_chat_with_messages(
        db,
        chat_id=chat_id,
        up_to_message_id=payload.up_to_message_id
    )
    if not new_chat:
        raise HTTPException(status_code=404, detail="Original chat not found or cannot be duplicated.")
    return new_chat


@router.post(
    "/archive",
    response_model=schemas.Chat,
    summary="新建文件夹并批量归档会话"
)
async def archive_chats_endpoint(
    request: schemas.ChatArchiveRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    接收一个名称和一组项目ID，创建一个新文件夹并将这些项目全部归档到入其中。
    """
    new_folder = await chat_service.archive_chats_to_new_folder(db, request=request)
    if not new_folder:
        raise HTTPException(status_code=400, detail="Failed to archive chats. Ensure requested items exist.")
    return new_folder
