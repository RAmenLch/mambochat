# backend/routers/kb_management.py

import json
from fastapi import APIRouter, Depends, status, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend import schemas
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import KBFileStatus
from backend.services.kb_service import KnowledgeBaseService
from backend.crud import kb_crud

router = APIRouter()


@router.post(
    "",
    response_model=schemas.Resource,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库"
)
async def create_knowledge_base(
        kb_data: kb_schemas.KBCreate,
        db: AsyncSession = Depends(get_db)
):
    """
    创建一个新的知识库资源（本质上是一个特殊的文件夹）。
    需要指定 Embedding 模型 ID。
    """
    service = KnowledgeBaseService(db)
    try:
        return await service.create_knowledge_base(kb_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- Moved from resource_management.py ---

@router.post(
    "/{resource_id}/task",
    status_code=status.HTTP_200_OK,
    summary="管理向量化任务"
)
async def run_kb_file_task(
        resource_id: str,
        request: kb_schemas.KBRunTaskRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    启动、恢复或停止资源的切分与嵌入任务。
    """
    service = KnowledgeBaseService(db)
    return await service.handle_task_action(resource_id, request)


@router.put(
    "/{resource_id}/config",
    response_model=schemas.Resource,
    status_code=status.HTTP_200_OK,
    summary="更新切分配置"
)
async def update_kb_file_config(
        resource_id: str,
        config_request: kb_schemas.KBUpdateConfigRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    更新资源的切分配置（Splitter Config）。
    配置存储在 Resource.kb_config 中。
    """
    service = KnowledgeBaseService(db)
    return await service.update_kb_file_config(resource_id, config_request)


@router.get(
    "/{resource_id}/progress",
    summary="订阅处理进度 (SSE)"
)
async def subscribe_kb_file_progress(resource_id: str):
    """
    订阅指定资源的处理进度。
    返回 Server-Sent Events (SSE) 流。
    包含 is_stale 状态以指示内容是否更新。
    """
    async def _stream_generator():
        # 1. 获取并推送初始状态
        async with AsyncSessionLocal() as session:
            service = KnowledgeBaseService(session)
            initial_status = await service.get_comprehensive_file_status(resource_id)

        yield f"data: {initial_status.model_dump_json()}\n\n"

        active_statuses = {
            KBFileStatus.CLEANING,
            KBFileStatus.READING,
            KBFileStatus.SPLITTING,
            KBFileStatus.EMBEDDING
        }

        if initial_status.file_status in active_statuses:
            # 导入 stream_manager 需注意循环依赖，这里局部导入或使用服务层
            from backend.services.stream_manager_service import stream_manager
            queue = await stream_manager.subscribe(resource_id)
            try:
                while True:
                    data = await queue.get()
                    if data is None:
                        yield f"event: end\ndata: Task finished\n\n"
                        break
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                    queue.task_done()
            except Exception:
                pass
            finally:
                await stream_manager.unsubscribe(resource_id, queue)
        else:
            yield f"event: end\ndata: Task finished\n\n"

    return StreamingResponse(
        _stream_generator(),
        media_type="text/event-stream"
    )


@router.post(
    "/search",
    response_model=kb_schemas.KBSearchResponse,
    summary="向量检索"
)
async def search_knowledge_base(
        request: kb_schemas.KBSearchRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    在知识库中进行语义搜索。
    返回结果包含切片索引 (chunk_index)。
    """
    service = KnowledgeBaseService(db)
    return await service.search_kb(request)


@router.get(
    "/{resource_id}/chunks",
    response_model=kb_schemas.KBChunkListResponse,
    summary="查询知识库文件切片列表"
)
async def get_resource_chunks(
        resource_id: str,
        min_index: int = Query(None, ge=0, description="切片索引最小值 (包含)"),
        max_index: int = Query(None, ge=0, description="切片索引最大值 (包含)"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        db: AsyncSession = Depends(get_db)
):
    """
    根据资源 ID 查询切片列表。
    支持按 chunk_index 范围筛选和分页。
    结果按 chunk_index 升序排列。
    """
    chunks, total = await kb_crud.get_chunks_by_resource_paginated(
        db=db,
        resource_id=resource_id,
        min_index=min_index,
        max_index=max_index,
        page=page,
        page_size=page_size
    )
    
    # 将 ORM 模型转换为 Pydantic 模型
    chunk_items = [kb_schemas.KBChunk.model_validate(chunk) for chunk in chunks]
    
    return kb_schemas.KBChunkListResponse(total=total, items=chunk_items)
