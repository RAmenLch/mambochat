# backend/crud/kb_crud.py

import json
from typing import List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased
from sqlalchemy import text, func, case, delete, update

from backend.models import kb_model, resource_model
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import KBFileStatus, ResourceType


# --- Chunk Management ---

async def batch_create_chunks(
        db: AsyncSession,
        chunks: List[kb_schemas.KBChunkCreate]
) -> bool:
    if not chunks:
        return True

    db_chunks = [
        kb_model.ResourceKBChunk(
            resource_id=chunk.resource_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            byte_size=chunk.byte_size,
            status=kb_schemas.KBChunkStatus.PENDING.value
        )
        for chunk in chunks
    ]
    db.add_all(db_chunks)
    await db.commit()
    return True


async def get_pending_chunks(
        db: AsyncSession,
        resource_id: str
) -> List[kb_model.ResourceKBChunk]:
    """获取所有状态为 PENDING 的切片"""
    result = await db.execute(
        select(kb_model.ResourceKBChunk)
        .filter(
            kb_model.ResourceKBChunk.resource_id == resource_id,
            kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.PENDING.value
        )
        .order_by(kb_model.ResourceKBChunk.chunk_index.asc())
    )
    return result.scalars().all()


async def get_chunks_by_statuses(
        db: AsyncSession,
        resource_id: str,
        statuses: List[str]
) -> List[kb_model.ResourceKBChunk]:
    """获取指定状态列表的切片，用于断点续连 (例如获取 PENDING 和 FAILED)"""
    result = await db.execute(
        select(kb_model.ResourceKBChunk)
        .filter(
            kb_model.ResourceKBChunk.resource_id == resource_id,
            kb_model.ResourceKBChunk.status.in_(statuses)
        )
        .order_by(kb_model.ResourceKBChunk.chunk_index.asc())
    )
    return result.scalars().all()


async def update_chunk_vector_id_and_status(
        db: AsyncSession,
        chunk_id: str,
        vector_id: Optional[int],
        status: kb_schemas.KBChunkStatus
) -> None:
    chunk = await db.get(kb_model.ResourceKBChunk, chunk_id)
    if chunk:
        chunk.vector_id = vector_id
        chunk.status = status.value
        await db.commit()


async def delete_chunks_by_resource(
        db: AsyncSession,
        resource_id: str
) -> None:
    """删除指定资源的所有切片记录"""
    await db.execute(
        delete(kb_model.ResourceKBChunk)
        .where(kb_model.ResourceKBChunk.resource_id == resource_id)
    )
    await db.commit()


async def mark_pending_chunks_as_stopped(
        db: AsyncSession,
        resource_id: str
) -> None:
    """将指定资源下所有状态为 PENDING 的切片更新为 STOPPED"""
    await db.execute(
        update(kb_model.ResourceKBChunk)
        .where(
            kb_model.ResourceKBChunk.resource_id == resource_id,
            kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.PENDING.value
        )
        .values(status=kb_schemas.KBChunkStatus.STOPPED.value)
    )
    await db.commit()


async def get_vector_ids_by_resource(
        db: AsyncSession,
        resource_id: str
) -> List[int]:
    """获取指定资源下所有已完成切片的 vector_id"""
    result = await db.execute(
        select(kb_model.ResourceKBChunk.vector_id)
        .filter(
            kb_model.ResourceKBChunk.resource_id == resource_id,
            kb_model.ResourceKBChunk.vector_id.is_not(None)
        )
    )
    return result.scalars().all()


async def get_chunk_stats_by_resource(
        db: AsyncSession,
        resource_id: str
) -> kb_schemas.KBProcessingStatus:
    stmt = select(
        func.count().label("total"),
        func.sum(case((kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.PENDING.value, 1), else_=0)).label(
            "pending"),
        func.sum(case((kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.COMPLETED.value, 1), else_=0)).label(
            "completed"),
        func.sum(case((kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.FAILED.value, 1), else_=0)).label(
            "failed"),
        func.sum(case((kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.STOPPED.value, 1), else_=0)).label(
            "stopped")
    ).filter(kb_model.ResourceKBChunk.resource_id == resource_id)

    result = await db.execute(stmt)
    row = result.one()

    total = row.total or 0
    pending = row.pending or 0
    completed = row.completed or 0
    failed = row.failed or 0
    stopped = row.stopped or 0

    # 基础状态判断，Service层会根据内存任务状态进行更精确的修正
    if total == 0:
        file_status = KBFileStatus.INITIAL
    elif failed > 0:
        file_status = KBFileStatus.FAILED
    elif stopped > 0:
        file_status = KBFileStatus.STOPPED
    elif pending > 0:
        # 在数据库层面，PENDING 代表尚未处理完成，映射为 EMBEDDING
        # Service 层如果知道正在 SPLITTING 或 READING，会覆盖此状态
        file_status = KBFileStatus.EMBEDDING
    elif total > 0 and total == completed:
        file_status = KBFileStatus.COMPLETED
    else:
        file_status = KBFileStatus.INITIAL

    return kb_schemas.KBProcessingStatus(
        resource_id=resource_id,
        total_chunks=total,
        pending_chunks=pending,
        completed_chunks=completed,
        failed_chunks=failed,
        stopped_chunks=stopped,
        file_status=file_status
    )


async def get_chunks_by_resource_paginated(
        db: AsyncSession,
        resource_id: str,
        min_index: Optional[int] = None,
        max_index: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
) -> Tuple[List[kb_model.ResourceKBChunk], int]:
    """
    通过 resource_id 查询切片，支持按 chunk_index 范围筛选和分页。
    """
    query = select(kb_model.ResourceKBChunk).filter(
        kb_model.ResourceKBChunk.resource_id == resource_id
    )

    if min_index is not None:
        query = query.filter(kb_model.ResourceKBChunk.chunk_index >= min_index)
    if max_index is not None:
        query = query.filter(kb_model.ResourceKBChunk.chunk_index <= max_index)

    query = query.order_by(kb_model.ResourceKBChunk.chunk_index.asc())

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return items, total


# --- Vector Operations (Raw SQL) ---

async def insert_vector(
        db: AsyncSession,
        dimension: int,
        vector: List[float]
) -> int:
    """
    将向量插入到指定维度的虚拟表中，并返回生成的 rowid。
    注意：sqlite-vec 的虚拟表可能不支持 RETURNING rowid，需使用 lastrowid 获取。
    """
    table_name = f"vec_dim_{dimension}"
    vector_json = json.dumps(vector)

    stmt = text(f"INSERT INTO {table_name} (vector) VALUES (:vector)")
    result = await db.execute(stmt, {"vector": vector_json})

    # 使用 result.lastrowid 获取插入后的 rowid
    rowid = result.lastrowid
    await db.commit()
    return rowid


async def delete_vectors(
        db: AsyncSession,
        dimension: int,
        rowids: List[int]
) -> None:
    """
    从指定维度的虚拟表中批量删除向量。
    """
    if not rowids:
        return

    table_name = f"vec_dim_{dimension}"
    # 将 rowids 转换为逗号分隔的字符串，注意安全，rowids 是 int 列表
    rowids_str = ",".join(map(str, rowids))

    stmt = text(f"DELETE FROM {table_name} WHERE rowid IN ({rowids_str})")
    await db.execute(stmt)
    await db.commit()


async def search_vectors(
        db: AsyncSession,
        dimension: int,
        query_vector: List[float],
        top_k: int
) -> List[Tuple[int, float]]:
    """
    在指定维度的向量表中搜索最近邻。
    """
    table_name = f"vec_dim_{dimension}"
    vector_json = json.dumps(query_vector)

    # 使用 'AND k = {top_k}' 显式约束，解决 sqlite-vec 优化器问题
    sql = f"""
        SELECT rowid, vec_distance_cosine(vector, :query_vector) as distance
        FROM {table_name}
        WHERE vector MATCH :query_vector
          AND k = {top_k}
        ORDER BY distance
    """

    stmt = text(sql)
    result = await db.execute(stmt, {"query_vector": vector_json})
    return result.all()


async def get_chunks_by_vector_ids(
        db: AsyncSession,
        vector_ids: List[int],
        kb_id_filter: Optional[str] = None
) -> List[Any]:
    """
    根据 vector_id 列表反查 Chunk 及其所属 Resource 和 KB 信息。
    支持多级目录结构 (Knowledge Base -> Folder -> File)。
    """
    if not vector_ids:
        return []

    # 1. CTE Base Part: 找到命中向量的文件资源
    # 我们需要保留原始文件的 ID 和 Name (origin_file_*)，以便最后输出
    # 同时获取其父级信息用于递归 (ancestor_*)
    # 使用 distinct 去重，防止同一个文件的多个 chunk 导致重复的递归起始点
    base_stmt = select(
        resource_model.Resource.id.label("ancestor_id"),
        resource_model.Resource.parentId.label("ancestor_parent_id"),
        resource_model.Resource.resourceType.label("ancestor_type"),
        resource_model.Resource.name.label("ancestor_name"),
        resource_model.Resource.id.label("origin_file_id"),
        resource_model.Resource.name.label("origin_file_name")
    ).join(
        kb_model.ResourceKBChunk, kb_model.ResourceKBChunk.resource_id == resource_model.Resource.id
    ).where(
        kb_model.ResourceKBChunk.vector_id.in_(vector_ids)
    ).distinct()

    cte = base_stmt.cte(name="kb_hierarchy", recursive=True)

    # 2. CTE Recursive Part: 向上查找父节点
    parent = aliased(resource_model.Resource)
    cte = cte.union_all(
        select(
            parent.id,
            parent.parentId,
            parent.resourceType,
            parent.name,
            cte.c.origin_file_id,
            cte.c.origin_file_name
        ).join(
            cte, parent.id == cte.c.ancestor_parent_id
        )
    )

    # 3. 主查询: 关联 Chunk 和 CTE
    # 筛选条件:
    # a. Chunk 的 vector_id 必须在列表中
    # b. CTE 中的 ancestor_type 必须是 KNOWLEDGE_BASE (找到根节点)
    query = select(
        kb_model.ResourceKBChunk,
        cte.c.origin_file_id.label("file_id"),
        cte.c.origin_file_name.label("file_name"),
        cte.c.ancestor_id.label("kb_id"),
        cte.c.ancestor_name.label("kb_name"),
        kb_model.ResourceKBChunk.chunk_index.label("chunk_index")
    ).join(
        cte, kb_model.ResourceKBChunk.resource_id == cte.c.origin_file_id
    ).where(
        kb_model.ResourceKBChunk.vector_id.in_(vector_ids),
        cte.c.ancestor_type == ResourceType.KNOWLEDGE_BASE.value
    )

    if kb_id_filter:
        query = query.where(cte.c.ancestor_id == kb_id_filter)

    result = await db.execute(query)
    return result.all()
