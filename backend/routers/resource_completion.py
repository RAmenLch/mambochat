# backend/routers/resource_completion.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.resource_completion import (
    ResourceCompletePathRequest,
    ResourceCompletePathResponse,
    ResourceContentCompleteRequest,
    ResourceContentCompleteResponse,
)
from backend.services import resource_completion_service

router = APIRouter(prefix="/resources/completion", tags=["Resource Completion"])


@router.post(
    "/path",
    response_model=ResourceCompletePathResponse,
    summary="资源路径补全（仅挂载 ResourceBackend 的 Agent 可用）",
)
async def complete_resource_path(
    request: ResourceCompletePathRequest,
    db: AsyncSession = Depends(get_db),
):
    enabled, items = await resource_completion_service.complete_path(
        db,
        agent_id=request.agent_id,
        prefix=request.prefix,
        limit=request.limit,
    )
    return {"enabled": enabled, "items": items}


@router.post(
    "/content",
    response_model=ResourceContentCompleteResponse,
    summary="资源内容续写补全（仅挂载 ResourceBackend 的 Agent 可用）",
)
async def complete_resource_content(
    request: ResourceContentCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    enabled, items = await resource_completion_service.complete_content(
        db,
        agent_id=request.agent_id,
        prefix=request.prefix,
        limit=request.limit,
        max_items=request.max_items,
    )
    return {"enabled": enabled, "items": items}
