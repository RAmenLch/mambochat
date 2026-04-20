# backend/routers/system_log.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.database import get_db
from backend.crud import log_crud
from backend.schemas.log import PaginatedPostLogResponse, PostLogResponse

router = APIRouter()


@router.get(
    "/post-payloads",
    response_model=PaginatedPostLogResponse,
    summary="分页获取发送给大模型的底层报文日志"
)
async def get_post_payload_logs(
        skip: int = Query(0, ge=0, description="跳过的记录数"),
        limit: int = Query(20, ge=1, le=100, description="每页返回的记录数"),
        chat_id: Optional[str] = Query(None, description="按会话ID过滤"),
        message_id: Optional[str] = Query(None, description="按消息ID过滤"),
        db: AsyncSession = Depends(get_db)
):
    """
    获取 MamboPostLog 列表，支持按 chat_id 和 message_id 过滤。
    默认按时间降序排列。
    """
    items, total = await log_crud.get_post_logs_paginated(
        db=db,
        skip=skip,
        limit=limit,
        chat_id=chat_id,
        message_id=message_id
    )

    # 显式将 ORM 模型转换为 Pydantic Schema，解决静态类型检查报警
    validated_items = [PostLogResponse.model_validate(item) for item in items]

    return PaginatedPostLogResponse(total=total, items=validated_items)

