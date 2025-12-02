# backend/routers/resource_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.crud import resource_crud
from backend import schemas
from backend.database import get_db

router = APIRouter(prefix="/resources", tags=["Resource Management"])


# MODIFIED: Changed path from "/" to "" to respond at /api/resources without a trailing slash.
@router.get("", response_model=List[schemas.Resource], summary="获取资源和文件夹列表")
async def read_resources(db: AsyncSession = Depends(get_db)):
    """
    获取所有资源和文件夹的列表，用于构建树状结构。
    """
    return await resource_crud.get_resources(db=db)


# MODIFIED: Changed path from "/" to "" to respond at /api/resources without a trailing slash.
@router.post("", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="创建新资源或文件夹")
async def create_resource(resource: schemas.ResourceCreate, db: AsyncSession = Depends(get_db)):
    """
    创建一个新的资源项（'resource'）或文件夹（'folder'）。
    如果创建的是资源，会自动为其生成一个初始的默认版本。
    """
    return await resource_crud.create_resource(db=db, resource=resource)


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


@router.post("/reorder", status_code=status.HTTP_200_OK, summary="批量更新资源排序")
async def reorder_resources(updates: List[schemas.ResourceReorderItem], db: AsyncSession = Depends(get_db)):
    """

    接收一个包含ID、新父ID和新排序顺序的列表，以批量更新项目层级和顺序。
    """
    await resource_crud.batch_update_resources_order(db, updates=updates)
    return {"message": "Reorder successful"}

