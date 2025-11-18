# backend/crud/resource_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

from ..models import resource_model
from .. import schemas


async def get_resource(db: AsyncSession, resource_id: str) -> Optional[resource_model.Resource]:
    """通过ID获取单个资源（包含其最新版本信息）。"""
    result = await db.execute(
        select(resource_model.Resource)
        .options(joinedload(resource_model.Resource.latest_version))
        .filter(resource_model.Resource.id == resource_id)
    )
    return result.scalars().first()


async def get_resources(db: AsyncSession) -> List[resource_model.Resource]:
    """获取所有资源和文件夹列表（按排序权重升序），并加载最新版本信息。"""
    result = await db.execute(
        select(resource_model.Resource)
        .options(joinedload(resource_model.Resource.latest_version))
        .order_by(resource_model.Resource.sortOrder.asc())
    )
    return result.scalars().all()


async def get_resource_with_versions(db: AsyncSession, resource_id: str) -> Optional[resource_model.Resource]:
    """通过ID获取单个资源及其所有版本列表。"""
    result = await db.execute(
        select(resource_model.Resource)
        .options(selectinload(resource_model.Resource.versions))
        .filter(resource_model.Resource.id == resource_id)
    )
    return result.scalars().first()


async def create_resource(db: AsyncSession, resource: schemas.ResourceCreate) -> resource_model.Resource:
    """创建一个新的资源或文件夹。如果创建的是资源，则自动为其生成一个初始版本。"""
    db_resource = resource_model.Resource(**resource.model_dump())
    db.add(db_resource)
    await db.flush()

    if db_resource.itemType == 'resource':
        initial_version = resource_model.ResourceVersion(
            resourceId=db_resource.id,
            name="初始版本",
            content=""
        )
        db.add(initial_version)
        await db.flush()

        db_resource.latestVersionId = initial_version.id

    await db.commit()

    # MODIFIED: 在 refresh 时，明确指定要预加载 latest_version 关系
    await db.refresh(db_resource, ['latest_version'])

    return db_resource


async def update_resource(db: AsyncSession, resource_id: str, resource_update: schemas.ResourceUpdate) -> Optional[
    resource_model.Resource]:
    """更新资源的基本信息，如名称、描述或父ID。"""
    db_resource = await get_resource(db, resource_id=resource_id)
    if not db_resource:
        return None

    update_data = resource_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_resource, key, value)

    await db.commit()
    await db.refresh(db_resource, ['latest_version'])  # 同样在此处添加预加载，保持一致性
    return db_resource


async def delete_resource(db: AsyncSession, resource_id: str) -> Optional[resource_model.Resource]:
    """删除一个资源或文件夹。"""
    # For delete operations, we don't need to load relationships for the response
    db_resource = await get_resource(db, resource_id=resource_id)
    if db_resource:
        await db.delete(db_resource)
        await db.commit()
    return db_resource


async def create_resource_version(db: AsyncSession, resource_id: str, version_create: schemas.ResourceVersionCreate) -> \
Optional[resource_model.ResourceVersion]:
    """为指定资源创建一个新的版本。"""
    db_resource = await get_resource(db, resource_id=resource_id)
    if not db_resource or db_resource.itemType != 'resource':
        return None

    new_version = resource_model.ResourceVersion(
        **version_create.model_dump(),
        resourceId=resource_id
    )
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    return new_version


async def update_resource_version(db: AsyncSession, version_id: str, version_update: schemas.ResourceVersionUpdate) -> \
Optional[resource_model.ResourceVersion]:
    """更新指定版本的内容和元数据。"""
    result = await db.execute(
        select(resource_model.ResourceVersion)
        .filter(resource_model.ResourceVersion.id == version_id)
    )
    db_version = result.scalars().first()

    if not db_version:
        return None

    update_data = version_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_version, key, value)

    await db.commit()
    await db.refresh(db_version)
    return db_version


async def set_active_version(db: AsyncSession, resource_id: str, version_id: str) -> Optional[resource_model.Resource]:
    """设置资源的活跃版本（更新latestVersionId指针）。"""
    db_resource = await get_resource(db, resource_id=resource_id)
    if not db_resource:
        return None

    result = await db.execute(
        select(resource_model.ResourceVersion)
        .filter(resource_model.ResourceVersion.id == version_id)
        .filter(resource_model.ResourceVersion.resourceId == resource_id)
    )
    db_version = result.scalars().first()
    if not db_version:
        return None

    db_resource.latestVersionId = version_id
    await db.commit()
    await db.refresh(db_resource, ['latest_version'])  # 同样在此处添加预加载
    return db_resource


async def batch_update_resources_order(db: AsyncSession, updates: List[schemas.ResourceReorderItem]) -> bool:
    """批量更新资源和文件夹的顺序与层级。"""
    if not updates:
        return True

    resource_ids = [item.id for item in updates]
    result = await db.execute(select(resource_model.Resource).filter(resource_model.Resource.id.in_(resource_ids)))
    resources_map = {res.id: res for res in result.scalars().all()}

    for update_item in updates:
        resource_to_update = resources_map.get(update_item.id)
        if resource_to_update:
            resource_to_update.parentId = update_item.parentId
            resource_to_update.sortOrder = update_item.sortOrder

    await db.commit()
    return True

