# backend/routers/resource_management.py

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import resource_crud, file_crud, kb_crud
from backend.database import get_db
from backend.models import resource_model
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import FileManagementType, ResourceType, ResourceItemType, KBFileStatus
from backend.services import chat_service, resource_service
from backend.services.kb_service import KnowledgeBaseService
from backend.services.storage_service import storage_service

router = APIRouter(prefix="/resources", tags=["Resource Management"])


# --- Basic Resource Operations ---

@router.get("", response_model=List[schemas.Resource], summary="获取资源和文件夹列表")
async def read_resources(db: AsyncSession = Depends(get_db)):
    """
    获取所有资源和文件夹的列表，用于构建树状结构。
    """
    return await resource_crud.get_resources(db=db)


@router.get("/children", response_model=List[schemas.ResourceSimple], summary="批量获取子资源和文件夹")
async def read_resource_children(
        parentIds: List[str] = Query(..., description="父节点ID列表，'root'代表根目录"),
        db: AsyncSession = Depends(get_db)
):
    """
    根据父节点ID列表并行加载子节点内容。
    """
    return await resource_crud.get_resources_by_parent_ids(db, parent_ids=parentIds)


@router.post("", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="创建新资源或文件夹")
async def create_resource(resource: schemas.ResourceCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的资源项（'resource'）或文件夹（'folder'）。
    """
    return await resource_crud.create_resource(db=db, resource=resource)


@router.post("/upload", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="上传资源文件")
async def upload_resource_file(
        file: UploadFile = File(...),
        parent_id: Optional[str] = Form(None, description="上传至指定文件夹ID (新建模式)"),
        resource_id: Optional[str] = Form(None, description="更新指定资源ID (更新模式)"),
        db: AsyncSession = Depends(get_db)
):
    """
    统一资源上传接口。
    - **新建模式**: 提供 parent_id (或 'root')，创建新 Resource (Type=FILE) 和 Version。
    - **更新模式**: 提供 resource_id，更新现有 Resource 的内容 (创建新 Version)。
    """
    if not parent_id and not resource_id:
        raise HTTPException(status_code=400, detail="Either parent_id or resource_id must be provided.")

    # 1. 保存物理文件
    try:
        storage_path = await storage_service.save(file, sub_path="resources")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File storage failed: {e}")

    db_file = await file_crud.create_file(
        db=db,
        filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        size=file.size,
        management_type=FileManagementType.RESOURCE.value
    )

    # 2. 场景 A: 新建资源
    if parent_id:
        # 检查是否在知识库内，以设置 kb_id
        kb_id = None
        kb_config = None

        if parent_id != "root":
            ancestors = await resource_crud.get_batch_resource_ancestors(db, [parent_id])
            kb_node = next((res for res in ancestors if res.resourceType == ResourceType.KNOWLEDGE_BASE.value), None)
            if kb_node:
                kb_id = kb_node.id
                # 设置默认切分配置
                kb_config = kb_schemas.KBTextSplitterConfig(
                    splitter_type=kb_schemas.KBSplitterType.SIMPLE,
                    chunk_size=500,
                    chunk_overlap=50
                ).model_dump()

        resource_create = schemas.ResourceCreate(
            name=file.filename,
            itemType=ResourceItemType.RESOURCE,
            resourceType=ResourceType.FILE,
            parentId=parent_id if parent_id != "root" else None,
            initial_content=db_file.id,
            initial_attributes={}
        )

        new_resource = await resource_crud.create_resource(db, resource_create)

        # 补充更新 kb_id 和 kb_config (如果存在)
        if kb_id:
            new_resource.kb_id = kb_id
            new_resource.kb_config = kb_config
            await db.commit()
            await db.refresh(new_resource)

        return new_resource

    # 3. 场景 B: 更新现有资源
    else:  # resource_id is not None
        resource = await resource_crud.get_resource_with_versions(db, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found.")

        if resource.itemType != ResourceItemType.RESOURCE.value:
            raise HTTPException(status_code=400, detail="Cannot upload content to a folder.")

        # 检查最新版本内容
        latest_ver = resource.latest_version

        if not latest_ver or not latest_ver.content:
            # 如果当前版本内容为空，直接更新当前版本
            await resource_crud.update_resource_version(
                db,
                resource.latestVersionId,
                schemas.ResourceVersionUpdate(content=db_file.id)
            )
        else:
            # 创建新版本
            new_version_data = schemas.ResourceVersionCreate(
                name=f"Update {file.filename}",
                content=db_file.id,
                attributes=latest_ver.attributes  # 继承属性
            )
            new_ver = await resource_crud.create_resource_version(db, resource_id, new_version_data)
            await resource_crud.set_active_version(db, resource_id, new_ver.id)

        await db.refresh(resource)
        return resource


@router.post("/move", status_code=status.HTTP_200_OK, summary="移动资源或文件夹")
async def move_resources(move_request: schemas.ResourceMoveRequest, db: AsyncSession = Depends(get_db)):
    """
    移动资源或文件夹到指定位置。
    自动处理知识库层级约束、kb_id 更新及向量清理等副作用。
    """
    success = await resource_service.move_resources(db, move_request)
    if not success:
        raise HTTPException(status_code=400, detail="Move operation failed")
    return {"message": "Move successful"}


@router.get("/{resource_id}", response_model=schemas.ResourceWithVersions, summary="获取单个资源的详细信息")
async def read_resource(resource_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取指定资源的详细信息，包括其所有版本快照的列表。
    """
    db_resource = await resource_crud.get_resource_with_versions(db, resource_id=resource_id)
    if not db_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return db_resource


@router.put("/{resource_id}", response_model=schemas.Resource, summary="更新资源基本信息")
async def update_resource(resource_id: str, resource_update: schemas.ResourceUpdate, db: AsyncSession = Depends(get_db)):
    """
    更新资源的基本信息，如名称、描述。
    注意：移动操作请使用 /move 接口。
    """
    updated_resource = await resource_crud.update_resource(db, resource_id=resource_id, resource_update=resource_update)
    if not updated_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return updated_resource


@router.delete("/{resource_id}", response_model=schemas.Resource, summary="删除资源或文件夹")
async def delete_resource(resource_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除指定的资源或文件夹及其所有子内容。
    会自动清理关联的向量数据和知识库切片。
    """
    # 1. 查找所有需要删除的资源ID（包括子孙节点）
    cte = select(resource_model.Resource.id, resource_model.Resource.kb_id).where(resource_model.Resource.id == resource_id).cte(name="hierarchy", recursive=True)
    child = resource_model.Resource
    cte = cte.union_all(select(child.id, child.kb_id).join(cte, child.parentId == cte.c.id))

    stmt = select(cte.c.id, cte.c.kb_id)
    result = await db.execute(stmt)
    rows = result.all()

    # 2. 遍历并清理向量
    kb_service = KnowledgeBaseService(db)

    for row in rows:
        target_id = row[0]
        target_kb_id = row[1]

        if target_kb_id:
            # 尝试获取 KB 的维度信息以清理向量
            try:
                kb_res = await resource_crud.get_resource_with_versions(db, target_kb_id)
                if kb_res and kb_res.latest_version and kb_res.latest_version.attributes:
                    dim = kb_res.latest_version.attributes.get("dimension")
                    if dim:
                        await kb_service._cleanup_vectors(target_id, dim)
            except Exception:
                pass

        # 清理 Chunk 表 (无论是否成功清理向量，都应清理 Chunk)
        await kb_crud.delete_chunks_by_resource(db, target_id)

    # 3. 执行级联删除
    deleted_resource = await resource_crud.delete_resource(db, resource_id=resource_id)
    if not deleted_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return deleted_resource


# --- Version Operations ---

@router.post("/{resource_id}/versions", response_model=schemas.ResourceVersion, status_code=status.HTTP_201_CREATED, summary="为资源创建新版本")
async def create_version_for_resource(resource_id: str, version_create: schemas.ResourceVersionCreate, db: AsyncSession = Depends(get_db)):
    """
    为指定的资源创建一个新的版本快照。
    """
    new_version = await resource_crud.create_resource_version(db, resource_id=resource_id, version_create=version_create)
    if not new_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found or is a folder")
    return new_version


@router.put("/versions/{version_id}", response_model=schemas.ResourceVersion, summary="更新指定版本")
async def update_version(version_id: str, version_update: schemas.ResourceVersionUpdate, db: AsyncSession = Depends(get_db)):
    """
    更新指定版本快照的内容、名称或其他元数据。
    """
    updated_version = await resource_crud.update_resource_version(db, version_id=version_id, version_update=version_update)
    if not updated_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource version not found")
    return updated_version


@router.put("/{resource_id}/set-active/{version_id}", response_model=schemas.Resource, summary="设置资源的活跃版本")
async def set_active_version(resource_id: str, version_id: str, db: AsyncSession = Depends(get_db)):
    """
    将资源的 'latestVersionId' 指针指向指定的版本ID。
    """
    updated_resource = await resource_crud.set_active_version(db, resource_id=resource_id, version_id=version_id)
    if not updated_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource or version not found")
    return updated_resource


# --- Search Operations ---

@router.post(
    "/search",
    response_model=schemas.ResourceSearchResponse,
    summary="全局搜索资源和版本内容"
)
async def search_resources(request: schemas.ResourceSearchRequest, db: AsyncSession = Depends(get_db)):
    """
    在资源标题、描述和最新版本内容中进行全局搜索。
    """
    skip = (request.page_num - 1) * request.page_size

    rows, total = await resource_crud.search_resources_and_versions(
        db,
        keyword=request.keyword,
        root_id=request.root_id,
        enable_regex=request.enable_regex,
        skip=skip,
        limit=request.page_size
    )

    if not rows:
        return schemas.ResourceSearchResponse(total=0, items=[])

    resource_ids = list({row.resource_id for row in rows})
    path_map = await resource_service.build_resource_paths(db, resource_ids)

    items = []
    for row in rows:
        context = chat_service.extract_context_snippet(
            content=row.raw_content,
            keyword=request.keyword,
            enable_regex=request.enable_regex
        )

        item = schemas.ResourceSearchResultItem(
            resource_id=row.resource_id,
            resource_name=row.resource_name,
            resource_path=path_map.get(row.resource_id, ""),
            match_type=row.match_type,
            context_text=context,
            version_id=row.version_id,
            updated_at=row.updated_at
        )
        items.append(item)

    return schemas.ResourceSearchResponse(total=total, items=items)


# --- Knowledge Base & Vector Operations (Migrated) ---

@router.post(
    "/kb/{resource_id}/task",
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
    "/kb/{resource_id}/config",
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
    "/kb/{resource_id}/progress",
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
        async with AsyncSession(resource_crud.AsyncSessionLocal().bind) as session:
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
    "/kb/search",
    response_model=kb_schemas.KBSearchResponse,
    summary="向量检索"
)
async def search_knowledge_base(
        request: kb_schemas.KBSearchRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    在知识库中进行语义搜索。
    """
    service = KnowledgeBaseService(db)
    return await service.search_kb(request)
