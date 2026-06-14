# backend/routers/agent_management.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.crud import agent_crud, file_crud
from backend import schemas
from backend.models import agent_model
from backend.database import get_db
from backend.services.file_service import FileService
from backend.services.resource_service import validate_mounted_resources, validate_memory_resources
from backend.schemas.enums import FileManagementType

router = APIRouter()


async def _attach_avatar_url(db: AsyncSession, agent: agent_model.Agent) -> schemas.AgentResponse:
    """辅助函数：将单个 ORM 模型转换为 Schema，并动态挂载头像 URL"""
    agent_resp = schemas.AgentResponse.model_validate(agent)
    if agent.agentAvatarId:
        file_service = FileService(db)
        file_record = await file_service.get_file(agent.agentAvatarId)
        if file_record:
            agent_resp.agentAvatarUrl = file_service.get_url(file_record.storage_path)
    return agent_resp


async def _attach_avatar_urls(db: AsyncSession, agents: List[agent_model.Agent]) -> List[schemas.AgentResponse]:
    """辅助函数：批量将 ORM 模型转换为 Schema，并动态挂载头像 URL（解决 N+1 查询问题）"""
    if not agents:
        return []

    agent_resps = [schemas.AgentResponse.model_validate(a) for a in agents]
    avatar_ids = [a.agentAvatarId for a in agents if a.agentAvatarId]

    if avatar_ids:
        files = await file_crud.get_files_by_ids(db, avatar_ids)
        file_service = FileService(db)
        url_map = {f.id: file_service.get_url(f.storage_path) for f in files}

        for resp in agent_resps:
            if resp.agentAvatarId and resp.agentAvatarId in url_map:
                resp.agentAvatarUrl = url_map[resp.agentAvatarId]

    return agent_resps


async def _validate_avatar_file(file: UploadFile):
    """辅助函数：用于校验上传的头像文件类型和大小"""
    ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types are: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024:.0f} MB."
        )


@router.post(
    "/agents/",
    response_model=schemas.AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新 Agent 或文件夹"
)
async def create_agent(agent: schemas.AgentCreate, db: AsyncSession = Depends(get_db)):
    if agent.resourcePromptList is not None:
        await validate_mounted_resources(db, agent.resourcePromptList)

    db_agent = await agent_crud.create_agent(db=db, agent=agent)
    return await _attach_avatar_url(db, db_agent)


@router.get(
    "/agents/",
    response_model=List[schemas.AgentResponse],
    summary="获取 Agent 和文件夹列表"
)
async def read_agents(skip: int = 0, limit: int = 1000, db: AsyncSession = Depends(get_db)):
    agents = await agent_crud.get_agents(db, skip=skip, limit=limit)
    return await _attach_avatar_urls(db, agents)


@router.get(
    "/agents/children",
    response_model=List[schemas.AgentResponse],
    summary="批量获取子 Agent 和文件夹"
)
async def read_agent_children(
        parentIds: List[str] = Query(..., description="父节点ID列表，'root'代表根目录"),
        db: AsyncSession = Depends(get_db)
):
    agents = await agent_crud.get_agents_by_parent_ids(db, parent_ids=parentIds)
    return await _attach_avatar_urls(db, agents)


@router.get(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="获取单个 Agent 或文件夹的配置"
)
async def read_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _attach_avatar_url(db, db_agent)


@router.put(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="更新 Agent 或文件夹配置"
)
async def update_agent_settings(
        agent_id: str,
        agent_update: schemas.AgentUpdate,
        db: AsyncSession = Depends(get_db)
):
    if agent_update.resourcePromptList is not None:
        await validate_mounted_resources(db, agent_update.resourcePromptList)

    if agent_update.memoryResourceIds is not None:
        await validate_memory_resources(db, agent_update.memoryResourceIds)
        # 合并 memory_resource_ids 到 agentParameters（enable_memory 由前端控制）
        current_params = agent_update.agentParameters or {}
        current_params["memory_resource_ids"] = agent_update.memoryResourceIds
        agent_update.agentParameters = current_params

    if agent_update.securityReviewConfig is not None:
        current_params = agent_update.agentParameters or {}
        current_params["security_review"] = agent_update.securityReviewConfig.model_dump()
        agent_update.agentParameters = current_params

    try:
        updated_agent = await agent_crud.update_agent(db, agent_id=agent_id, agent_update=agent_update)
        if updated_agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return await _attach_avatar_url(db, updated_agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="删除 Agent 或文件夹"
)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    db_agent = await agent_crud.delete_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    # 删除时返回最后的状态，同样附带 URL
    return await _attach_avatar_url(db, db_agent)


@router.post(
    "/agents/move",
    status_code=status.HTTP_200_OK,
    summary="移动 Agent 或文件夹"
)
async def move_agents(move_request: schemas.AgentMoveRequest, db: AsyncSession = Depends(get_db)):
    success = await agent_crud.move_agents(db, move_request=move_request)
    if not success:
        raise HTTPException(status_code=400, detail="Move operation failed")
    return {"message": "Move successful"}


@router.put(
    "/agents/{agent_id}/avatar",
    response_model=schemas.File,
    summary="上传 Agent 头像"
)
async def upload_agent_avatar(
        agent_id: str,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    await _validate_avatar_file(file)

    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_avatar_id = db_agent.agentAvatarId

    file_service = FileService(db)

    # 1. 保存新头像文件
    new_file_record = await file_service.save_file(
        file=file,
        management_type=[FileManagementType.AGENT_AVATAR.value],
        sub_path="avatars"
    )

    # 2. 更新 Agent 的 agentAvatarId
    await agent_crud.update_agent(
        db,
        agent_id=agent_id,
        agent_update=schemas.AgentUpdate(agentAvatarId=new_file_record.id)
    )

    # 3. 删除旧头像文件防止存储堆积
    if old_avatar_id:
        await file_service.delete_file(old_avatar_id)

    return file_service.convert_to_schema(new_file_record)


@router.delete(
    "/agents/{agent_id}/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Agent 头像"
)
async def delete_agent_avatar(
        agent_id: str,
        db: AsyncSession = Depends(get_db)
):
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_avatar_id = db_agent.agentAvatarId
    if not old_avatar_id:
        return None

    file_service = FileService(db)

    # 1. 删除头像文件
    await file_service.delete_file(old_avatar_id)

    # 2. 将 Agent 的 agentAvatarId 设为空
    await agent_crud.update_agent(
        db,
        agent_id=agent_id,
        agent_update=schemas.AgentUpdate(agentAvatarId=None)
    )

    return None
