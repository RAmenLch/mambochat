# backend/crud/log_crud.py

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from backend.models.log_model import MamboPostLog


async def create_post_log(db: AsyncSession, log_data: Dict[str, Any]) -> MamboPostLog:
    """
    创建一个新的底层报文日志记录
    """
    db_log = MamboPostLog(**log_data)
    db.add(db_log)
    await db.commit()
    await db.refresh(db_log)
    return db_log


async def get_post_logs_paginated(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    chat_id: Optional[str] = None,
    message_id: Optional[str] = None
) -> Tuple[List[MamboPostLog], int]:
    """
    分页获取底层报文日志记录，支持按 chatId 和 messageId 过滤，按创建时间降序排列
    """
    # 基础查询
    query = select(MamboPostLog)
    count_query = select(func.count()).select_from(MamboPostLog)

    # 动态构建过滤条件
    filters = []
    if chat_id:
        filters.append(MamboPostLog.chatId == chat_id)
    if message_id:
        filters.append(MamboPostLog.messageId == message_id)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    # 获取总数
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    if total == 0:
        return [], 0

    # 获取分页数据 (按 createdAt 降序)
    query = query.order_by(MamboPostLog.createdAt.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total

