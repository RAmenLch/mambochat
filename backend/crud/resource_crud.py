# backend/crud/resource_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func, or_, update, literal, null, case, union_all
from typing import List, Optional, Tuple, Any

from backend.models import resource_model
from backend.schemas.enums import MoveAction, ResourceItemType
from backend import schemas


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


async def get_resources_by_ids(db: AsyncSession, resource_ids: List[str]) -> List[resource_model.Resource]:
    """
    根据ID列表批量获取资源对象。
    自动预加载 latest_version 关系数据。
    """
    if not resource_ids:
        return []

    result = await db.execute(
        select(resource_model.Resource)
        .options(joinedload(resource_model.Resource.latest_version))
        .filter(resource_model.Resource.id.in_(resource_ids))
    )
    return result.scalars().all()


async def get_resources_by_parent_ids(db: AsyncSession, parent_ids: List[str]) -> List[resource_model.Resource]:
    """
    根据父节点ID列表批量获取子资源和文件夹。
    如果列表中包含 "root"，则同时获取根目录下的项目。
    注意：此方法不加载 latest_version 的详细内容。
    """
    if not parent_ids:
        return []

    conditions = []
    valid_uuids = [pid for pid in parent_ids if pid != "root"]

    if valid_uuids:
        conditions.append(resource_model.Resource.parentId.in_(valid_uuids))

    if "root" in parent_ids:
        conditions.append(resource_model.Resource.parentId.is_(None))

    if not conditions:
        return []

    result = await db.execute(
        select(resource_model.Resource)
        .filter(or_(*conditions))
        .order_by(resource_model.Resource.sortOrder.asc())
    )
    return result.scalars().all()


async def get_child_names_by_parent_id(db: AsyncSession, parent_id: Optional[str]) -> List[str]:
    """
    获取指定父节点下所有直接子资源的名称列表，用于冲突检测。
    """
    stmt = select(resource_model.Resource.name)
    if parent_id is None:
        stmt = stmt.filter(resource_model.Resource.parentId.is_(None))
    else:
        stmt = stmt.filter(resource_model.Resource.parentId == parent_id)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_resource_with_versions(db: AsyncSession, resource_id: str) -> Optional[resource_model.Resource]:
    """通过ID获取单个资源及其所有版本列表。"""
    result = await db.execute(
        select(resource_model.Resource)
        .options(selectinload(resource_model.Resource.versions), joinedload(resource_model.Resource.latest_version))
        .filter(resource_model.Resource.id == resource_id)
    )
    return result.scalars().first()


async def create_resource(db: AsyncSession, resource: schemas.ResourceCreate) -> resource_model.Resource:
    """创建一个新的资源或文件夹。如果创建的是资源，则自动为其生成一个初始版本。"""

    # 如果未传 sortOrder，则计算追加到末尾的顺序值
    if "sortOrder" not in resource.model_fields_set:
        stmt = select(func.max(resource_model.Resource.sortOrder)).filter(
            resource_model.Resource.parentId == resource.parentId
        )
        result = await db.execute(stmt)
        max_order = result.scalar()
        resource.sortOrder = (max_order if max_order is not None else -1) + 1

    # 排除非模型字段，以创建 Resource 实例
    resource_data = resource.model_dump(exclude={'initial_content', 'initial_attributes'})

    # 显式处理枚举转字符串，确保兼容性
    if 'itemType' in resource_data and hasattr(resource_data['itemType'], 'value'):
        resource_data['itemType'] = resource_data['itemType'].value
    if 'resourceType' in resource_data and resource_data['resourceType'] and hasattr(resource_data['resourceType'],
                                                                                     'value'):
        resource_data['resourceType'] = resource_data['resourceType'].value

    db_resource = resource_model.Resource(**resource_data)
    db.add(db_resource)
    await db.flush()

    # 使用枚举值进行判断
    if db_resource.itemType == ResourceItemType.RESOURCE.value:
        # 使用请求中提供的初始值创建初始版本
        initial_version = resource_model.ResourceVersion(
            resourceId=db_resource.id,
            name="v1",
            content=resource.initial_content or "",
            attributes=resource.initial_attributes
        )
        db.add(initial_version)
        await db.flush()

        db_resource.latestVersionId = initial_version.id

    await db.commit()

    # 刷新对象以加载所有属性，包括新链接的 latest_version
    await db.refresh(db_resource)
    if db_resource.latestVersionId:
        # 确保在刷新后填充关系属性
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
    await db.refresh(db_resource)
    return db_resource


async def delete_resource(db: AsyncSession, resource_id: str) -> Optional[resource_model.Resource]:
    """删除一个资源或文件夹。"""
    db_resource = await get_resource(db, resource_id=resource_id)
    if db_resource:
        await db.delete(db_resource)
        await db.commit()
    return db_resource


async def create_resource_version(db: AsyncSession, resource_id: str, version_create: schemas.ResourceVersionCreate) -> \
        Optional[resource_model.ResourceVersion]:
    """为指定资源创建一个新的版本。"""
    db_resource = await get_resource(db, resource_id=resource_id)

    # 使用枚举值进行判断
    # 注意: 并非Folder类型不可创建version,而是普通的Folder不创建version,如KB在其自有的服务会创建version
    if not db_resource or db_resource.itemType != ResourceItemType.RESOURCE.value:
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
    result = await db.execute(select(resource_model.Resource).filter(resource_model.Resource.id == resource_id))
    db_resource = result.scalars().first()
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

    await db.refresh(db_resource)
    await db.refresh(db_resource, ['latest_version'])

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


async def move_resources(db: AsyncSession, move_request: schemas.ResourceMoveRequest) -> bool:
    """
    移动资源或文件夹到指定位置。
    处理目标位置的排序挤占逻辑。
    """
    if not move_request.item_ids:
        return True

    target_parent_id = None
    target_sort_order = 0

    if move_request.action == MoveAction.INSIDE:
        if move_request.reference_id != "root":
            target_parent_id = move_request.reference_id

        stmt = select(func.max(resource_model.Resource.sortOrder)).filter(
            resource_model.Resource.parentId == target_parent_id)
        result = await db.execute(stmt)
        max_order = result.scalar()
        target_sort_order = (max_order if max_order is not None else -1) + 1

    else:
        if move_request.reference_id == "root":
            return False

        ref_resource = await db.get(resource_model.Resource, move_request.reference_id)
        if not ref_resource:
            return False

        target_parent_id = ref_resource.parentId
        base_order = ref_resource.sortOrder

        if move_request.action == MoveAction.BEFORE:
            target_sort_order = base_order
        else:  # AFTER
            target_sort_order = base_order + 1

        shift_stmt = (
            update(resource_model.Resource)
            .where(resource_model.Resource.parentId == target_parent_id)
            .where(resource_model.Resource.sortOrder >= target_sort_order)
            .values(sortOrder=resource_model.Resource.sortOrder + len(move_request.item_ids))
        )
        await db.execute(shift_stmt)

    for index, item_id in enumerate(move_request.item_ids):
        stmt = (
            update(resource_model.Resource)
            .where(resource_model.Resource.id == item_id)
            .values(
                parentId=target_parent_id,
                sortOrder=target_sort_order + index
            )
        )
        await db.execute(stmt)

    await db.commit()
    return True


async def search_resources_and_versions(
        db: AsyncSession,
        keyword: str,
        root_id: Optional[str],
        enable_regex: bool,
        skip: int,
        limit: int
) -> Tuple[List[Any], int]:
    """
    全局搜索资源名称、描述以及最新版本的内容。
    返回: (结果列表, 总数)
    结果列表中的每一项包含: resource_id, resource_name, version_id, raw_content, match_type, updated_at
    """

    # 1. 准备过滤条件
    if enable_regex:
        # 使用 SQLite 自定义函数 REGEXP
        def match_op(column):
            return column.op("REGEXP")(keyword)
    else:
        # 使用 LIKE 模糊匹配
        search_pattern = f"%{keyword}%"

        def match_op(column):
            return column.like(search_pattern)

    # 2. 如果指定了 root_id，构建递归 CTE 以获取所有子孙 Resource ID
    target_resource_ids_query = None
    if root_id:
        hierarchy_cte = select(resource_model.Resource.id).where(
            resource_model.Resource.id == root_id
        ).cte(name="hierarchy", recursive=True)

        hierarchy_cte = hierarchy_cte.union_all(
            select(resource_model.Resource.id).join(
                hierarchy_cte, resource_model.Resource.parentId == hierarchy_cte.c.id
            )
        )
        target_resource_ids_query = select(hierarchy_cte.c.id)

    # 3. 构建 ResourceVersion 内容搜索查询 (仅搜索最新版本)
    # Join Resource 表以获取 latestVersionId，并确保只搜索当前活跃的版本
    q_content = select(
        resource_model.Resource.id.label("resource_id"),
        resource_model.Resource.name.label("resource_name"),
        resource_model.ResourceVersion.id.label("version_id"),
        resource_model.ResourceVersion.content.label("raw_content"),
        literal("content").label("match_type"),
        resource_model.ResourceVersion.updatedAt.label("updated_at")
    ).join(
        resource_model.ResourceVersion,
        resource_model.Resource.latestVersionId == resource_model.ResourceVersion.id
    ).where(
        # 使用枚举值进行判断
        resource_model.Resource.itemType == ResourceItemType.RESOURCE.value,
        match_op(resource_model.ResourceVersion.content)
    )

    if target_resource_ids_query is not None:
        q_content = q_content.where(resource_model.Resource.id.in_(target_resource_ids_query))

    # 4. 构建 Resource 元数据 搜索查询
    name_match = match_op(resource_model.Resource.name)
    desc_match = match_op(resource_model.Resource.description)

    q_meta = select(
        resource_model.Resource.id.label("resource_id"),
        resource_model.Resource.name.label("resource_name"),
        null().label("version_id"),
        case(
            (name_match, resource_model.Resource.name),
            else_=resource_model.Resource.description
        ).label("raw_content"),
        case(
            (name_match, literal("name")),
            else_=literal("description")
        ).label("match_type"),
        resource_model.Resource.updatedAt.label("updated_at")
    ).where(
        # 使用枚举值进行判断
        resource_model.Resource.itemType == ResourceItemType.RESOURCE.value,
        (name_match | desc_match)
    )

    if target_resource_ids_query is not None:
        q_meta = q_meta.where(resource_model.Resource.id.in_(target_resource_ids_query))

    # 5. 合并查询
    union_query = union_all(q_content, q_meta).subquery()

    # 6. 获取总数
    count_stmt = select(func.count()).select_from(union_query)
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    if total_count == 0:
        return [], 0

    # 7. 获取分页结果
    stmt = select(union_query).order_by(union_query.c.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total_count


async def get_batch_resource_ancestors(db: AsyncSession, resource_ids: List[str]) -> List[resource_model.Resource]:
    """
    批量获取指定资源列表的所有祖先节点（包括自身），用于构建路径。
    """
    if not resource_ids:
        return []

    # 1. 递归 CTE: 只查询 ID 和 parentId 以建立层级关系
    cte = select(
        resource_model.Resource.id,
        resource_model.Resource.parentId
    ).where(resource_model.Resource.id.in_(resource_ids)).cte(name="ancestors", recursive=True)

    # 递归部分：查找父节点
    cte = cte.union_all(
        select(
            resource_model.Resource.id,
            resource_model.Resource.parentId
        ).join(cte, resource_model.Resource.id == cte.c.parentId)
    )

    # 2. 获取所有涉及的 ID
    stmt = select(cte.c.id)
    result = await db.execute(stmt)
    ancestor_ids = result.scalars().all()

    if not ancestor_ids:
        return []

    # 3. 查询完整的 ORM 对象
    resources_result = await db.execute(
        select(resource_model.Resource)
        .options(joinedload(resource_model.Resource.latest_version))
        .where(resource_model.Resource.id.in_(ancestor_ids))
    )

    return resources_result.scalars().all()


async def get_skill_descendants_with_versions(db: AsyncSession, skill_ids: List[str]) -> List[resource_model.Resource]:
    """
    根据 SKILL 根节点 ID 列表，递归获取其下所有的子孙节点（包含文件夹和文件）。
    自动预加载 latest_version 关系数据，以便后续提取底层物理文件 ID。
    """
    if not skill_ids:
        return []

    # 1. 递归 CTE: 查询所有子孙节点的 ID
    # 基础查询：选出指定的 SKILL 根节点
    cte = select(
        resource_model.Resource.id,
        resource_model.Resource.parentId
    ).where(resource_model.Resource.id.in_(skill_ids)).cte(name="skill_descendants", recursive=True)

    # 递归部分：查找 parentId 等于当前节点 id 的子节点
    cte = cte.union_all(
        select(
            resource_model.Resource.id,
            resource_model.Resource.parentId
        ).join(cte, resource_model.Resource.parentId == cte.c.id)
    )

    # 获取所有涉及的节点 ID
    stmt = select(cte.c.id)
    result = await db.execute(stmt)
    descendant_ids = result.scalars().all()

    if not descendant_ids:
        return []

    # 2. 查询完整的 ORM 对象并预加载 latest_version
    resources_result = await db.execute(
        select(resource_model.Resource)
        .options(joinedload(resource_model.Resource.latest_version))
        .where(resource_model.Resource.id.in_(descendant_ids))
    )

    return list(resources_result.scalars().all())
