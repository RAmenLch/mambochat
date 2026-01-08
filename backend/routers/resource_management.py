# backend/routers/resource_management.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.crud import resource_crud
from backend import schemas
from backend.database import get_db
from backend.services import chat_service, resource_service

router = APIRouter(prefix="/resources", tags=["Resource Management"])


# MODIFIED: Changed path from "/" to "" to respond at /api/resources without a trailing slash.
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
    注意：此接口返回轻量级对象，不包含 latest_version 信息。
    """
    return await resource_crud.get_resources_by_parent_ids(db, parent_ids=parentIds)


# MODIFIED: Changed path from "/" to "" to respond at /api/resources without a trailing slash.
@router.post("", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="创建新资源或文件夹")
async def create_resource(resource: schemas.ResourceCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的资源项（'resource'）或文件夹（'folder'）。
    如果创建的是资源，会自动为其生成一个初始的默认版本。
    """
    return await resource_crud.create_resource(db=db, resource=resource)


@router.post("/move", status_code=status.HTTP_200_OK, summary="移动资源或文件夹")
async def move_resources(move_request: schemas.ResourceMoveRequest, db: AsyncSession = Depends(get_db)):
    """
    移动资源或文件夹到指定位置（Inside, Before, After）。
    """
    success = await resource_crud.move_resources(db, move_request=move_request)
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
    更新资源的基本信息，如名称、描述或所属文件夹。
    """
    updated_resource = await resource_crud.update_resource(db, resource_id=resource_id, resource_update=resource_update)
    if not updated_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return updated_resource


@router.delete("/{resource_id}", response_model=schemas.Resource, summary="删除资源或文件夹")
async def delete_resource(resource_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除指定的资源或文件夹及其所有子内容。
    """
    deleted_resource = await resource_crud.delete_resource(db, resource_id=resource_id)
    if not deleted_resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return deleted_resource


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource or version not found, or version does not belong to resource")
    return updated_resource


@router.post("/reorder", status_code=status.HTTP_200_OK, summary="批量更新资源排序 (Deprecated)")
async def reorder_resources(updates: List[schemas.ResourceReorderItem], db: AsyncSession = Depends(get_db)):
    """
    接收一个包含ID、新父ID和新排序顺序的列表，以批量更新项目层级和顺序。
    Note: This endpoint is deprecated in favor of /resources/move.
    """
    await resource_crud.batch_update_resources_order(db, updates=updates)
    return {"message": "Reorder successful"}

@router.post(
    "/search",
    response_model=schemas.ResourceSearchResponse,
    summary="全局搜索资源和版本内容"
)
async def search_resources(request: schemas.ResourceSearchRequest, db: AsyncSession = Depends(get_db)):
    """
    在资源标题、描述和最新版本内容中进行全局搜索。
    支持模糊查询和正则查询，支持指定目录范围。
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

    # 提取所有涉及的 resource_id，批量构建路径
    resource_ids = list({row.resource_id for row in rows})
    path_map = await resource_service.build_resource_paths(db, resource_ids)

    items = []
    for row in rows:
        # 截取上下文
        # 复用 chat_service 中的逻辑以保持统一的高亮体验
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