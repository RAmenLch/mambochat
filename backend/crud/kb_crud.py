# backend/crud/kb_crud.py

import json
from typing import List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased
from sqlalchemy import text, func, case

from backend.models import kb_model, resource_model
from backend.schemas import kb as kb_schemas


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
    result = await db.execute(
        select(kb_model.ResourceKBChunk)
        .filter(
            kb_model.ResourceKBChunk.resource_id == resource_id,
            kb_model.ResourceKBChunk.status == kb_schemas.KBChunkStatus.PENDING.value
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
            "failed")
    ).filter(kb_model.ResourceKBChunk.resource_id == resource_id)

    result = await db.execute(stmt)
    row = result.one()

    total = row.total or 0
    pending = row.pending or 0
    completed = row.completed or 0
    failed = row.failed or 0

    if failed > 0:
        file_status = "FAILED"
    elif pending > 0:
        file_status = "PROCESSING"
    else:
        file_status = "INDEXED"

    return kb_schemas.KBProcessingStatus(
        resource_id=resource_id,
        total_chunks=total,
        pending_chunks=pending,
        completed_chunks=completed,
        failed_chunks=failed,
        file_status=file_status
    )


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
        SELECT rowid, vec_distance_L2(vector, :query_vector) as distance
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
    如果提供了 kb_id_filter，则进行过滤。
    """
    if not vector_ids:
        return []

    # 使用 aliased 创建真正的 SQL 别名，避免 ambiguous column name 错误
    FileResource = aliased(resource_model.Resource, name="file_resource")
    KBResource = aliased(resource_model.Resource, name="kb_resource")

    query = select(
        kb_model.ResourceKBChunk,
        FileResource.id.label("file_id"),
        FileResource.name.label("file_name"),
        KBResource.id.label("kb_id"),
        KBResource.name.label("kb_name")
    ).join(
        FileResource, kb_model.ResourceKBChunk.resource_id == FileResource.id
    ).join(
        KBResource, FileResource.parentId == KBResource.id
    ).filter(
        kb_model.ResourceKBChunk.vector_id.in_(vector_ids)
    )

    if kb_id_filter:
        # 这里使用别名 KBResource 进行过滤
        query = query.filter(KBResource.id == kb_id_filter)

    result = await db.execute(query)
    return result.all()
