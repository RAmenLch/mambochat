# backend/routers/resource_management.py

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import resource_crud, kb_crud
from backend.database import get_db, AsyncSessionLocal
from backend.models import resource_model
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import FileManagementType, ResourceType, ResourceItemType, KBFileStatus
from backend.services import chat_service, resource_service
from backend.services.kb_service import KnowledgeBaseService
from backend.services.file_service import FileService

router = APIRouter(prefix="/resources", tags=["Resource Management"])


async def _hydrate_resources(resources: List[schemas.Resource], db: AsyncSession):
    """
    批量填充资源的 file_info 信息。
    针对 ResourceType 为 FILE 或 KB_FILE 的资源。
    会检查 latest_version 以及 versions 列表（如果存在）。
    """
    if not resources:
        return

    # 显式加载 latest_version 和 versions 关系
    # 防止因 session.refresh() 或查询未包含关系时，访问属性触发懒加载报错
    resource_ids = [r.id for r in resources]
    if resource_ids:
        await db.execute(
            select(resource_model.Resource)
            .options(
                selectinload(resource_model.Resource.latest_version),
                selectinload(resource_model.Resource.versions)
            )
            .filter(resource_model.Resource.id.in_(resource_ids))
        )

    # 1. 收集需要查询的文件ID
    file_ids = set()
    # 映射: file_id -> list of version objects to update
    version_map = {}

    def _collect_file_id(version_obj):
        if not version_obj or not version_obj.content:
            return
        fid = version_obj.content
        file_ids.add(fid)
        if fid not in version_map:
            version_map[fid] = []
        version_map[fid].append(version_obj)

    for res in resources:
        # 必须是文件类型的资源
        if res.resourceType not in [ResourceType.FILE.value, ResourceType.KB_FILE.value]:
            continue

        # 1. 处理最新版本
        if hasattr(res, 'latest_version') and res.latest_version:
            _collect_file_id(res.latest_version)

        # 2. 处理历史版本列表 (仅当属性存在且非空时)
        if hasattr(res, 'versions') and res.versions:
            for ver in res.versions:
                _collect_file_id(ver)

    if not file_ids:
        return

    # 2. 批量查询文件信息
    file_service = FileService(db)
    file_records = await file_service.batch_get_files(list(file_ids))

    # 3. 填充信息
    for record in file_records:
        file_info = file_service.convert_to_schema(record)

        # 将文件信息回填到所有引用该文件的版本对象中
        if record.id in version_map:
            for version_obj in version_map[record.id]:
                version_obj.file_info = file_info


# --- Basic Resource Operations ---

@router.get("", response_model=List[schemas.Resource], summary="获取资源和文件夹列表")
async def read_resources(db: AsyncSession = Depends(get_db)):
    """
    获取所有资源和文件夹的列表，用于构建树状结构。
    """
    resources = await resource_crud.get_resources(db=db)
    # 填充文件详情
    await _hydrate_resources(resources, db)
    return resources


@router.get("/children", response_model=List[schemas.ResourceSimple], summary="批量获取子资源和文件夹")
async def read_resource_children(
        parentIds: List[str] = Query(..., description="父节点ID列表，'root'代表根目录"),
        db: AsyncSession = Depends(get_db)
):
    """
    根据父节点ID列表并行加载子节点内容。
    注意：此接口返回 ResourceSimple，不包含 latest_version，因此不进行文件详情填充。
    """
    return await resource_crud.get_resources_by_parent_ids(db, parent_ids=parent_ids)


@router.post("", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="创建新资源或文件夹")
async def create_resource(resource: schemas.ResourceCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的资源项（'resource'）或 'folder'）。
    """
    # 1. 先创建资源
    new_resource = await resource_crud.create_resource(db=db, resource=resource)

    # 2. 补充逻辑：如果提供了 parentId 且不是 root，尝试自动推导并赋值 kb_id
    # 这样可以确保在知识库下新建资源时，自动成为知识库成员
    if resource.parentId and resource.parentId != "root" and not new_resource.kb_id:
        ancestors = await resource_crud.get_batch_resource_ancestors(db, [resource.parentId])
        kb_node = next((res for res in ancestors if res.resourceType == ResourceType.KNOWLEDGE_BASE.value), None)

        if kb_node:
            # 赋值 kb_id
            new_resource.kb_id = kb_node.id

            # 如果是资源类型（非文件夹），且没有配置切分参数，设置默认配置
            if new_resource.itemType == ResourceItemType.RESOURCE.value and not new_resource.kb_config:
                default_config = kb_schemas.KBTextSplitterConfig(
                    splitter_type=kb_schemas.KBSplitterType.SIMPLE,
                    chunk_size=500,
                    chunk_overlap=50
                ).model_dump()
                new_resource.kb_config = default_config

            # 提交更改
            await db.commit()
            await db.refresh(new_resource)

    # 如果创建时带有初始内容（文件ID），尝试填充
    await _hydrate_resources([new_resource], db)
    return new_resource


@router.post("/upload", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="上传资源文件")
async def upload_resource_file(
        file: UploadFile = File(...),
        parent_id: Optional[str] = Form(None, description="上传至指定文件夹ID (新建模式)"),
        resource_id: Optional[str] = Form(None, description="更新指定资源ID (更新模式)"),
        db: AsyncSession = Depends(get_db)
):
    if not parent_id and not resource_id:
        raise HTTPException(status_code=400, detail="Either parent_id or resource_id must be provided.")

    file_service = FileService(db)

    db_file = await file_service.save_file(
        file=file,
        management_type=[FileManagementType.RESOURCE.value],
        sub_path="resources"
    )

    result_resource = None

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

        result_resource = new_resource

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
        result_resource = resource

    # 填充文件详情
    if result_resource:
        await _hydrate_resources([result_resource], db)

    return result_resource


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

    # 填充文件详情 (包含 latest_version 和 versions 列表)
    await _hydrate_resources([db_resource], db)
    return db_resource


@router.put("/{resource_id}", response_model=schemas.Resource, summary="更新资源基本信息")
async def update_resource(resource_id: str, resource_update: schemas.ResourceUpdate,
                          db: AsyncSession = Depends(get_db)):
    """
    更新资源的基本信息，如名称、描述。
    注意：移动操作请使用 /move 接口。
    """
    updated_resource = await resource_crud.update_resource(db, resource_id=resource_id, resource_update=resource_update)
    if not updated_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    # 填充文件详情
    await _hydrate_resources([updated_resource], db)
    return updated_resource


@router.delete("/{resource_id}", response_model=schemas.Resource, summary="删除资源或文件夹")
async def delete_resource(resource_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除指定的资源或文件夹及其所有子内容。
    会自动清理关联的向量数据和知识库切片。
    """
    # 1. 查找所有需要删除的资源ID（包括子孙节点）
    cte = select(resource_model.Resource.id, resource_model.Resource.kb_id).where(
        resource_model.Resource.id == resource_id).cte(name="hierarchy", recursive=True)
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

@router.post("/{resource_id}/versions", response_model=schemas.ResourceVersion, status_code=status.HTTP_201_CREATED,
             summary="为资源创建新版本")
async def create_version_for_resource(resource_id: str, version_create: schemas.ResourceVersionCreate,
                                      db: AsyncSession = Depends(get_db)):
    """
    为指定的资源创建一个新的版本快照。
    """
    new_version = await resource_crud.create_resource_version(db, resource_id=resource_id,
                                                              version_create=version_create)
    if not new_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found or is a folder")
    return new_version


@router.put("/versions/{version_id}", response_model=schemas.ResourceVersion, summary="更新指定版本")
async def update_version(version_id: str, version_update: schemas.ResourceVersionUpdate,
                         db: AsyncSession = Depends(get_db)):
    """
    更新指定版本快照的内容、名称或其他元数据。
    """
    updated_version = await resource_crud.update_resource_version(db, version_id=version_id,
                                                                  version_update=version_update)
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

    # 填充文件详情
    await _hydrate_resources([updated_resource], db)
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
