# backend/crud/resource_completion_crud.py

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import file_model, resource_model


async def get_descendants_brief(
    db: AsyncSession,
    root_ids: List[str],
) -> List[resource_model.Resource]:
    """递归获取多个根节点下的全部子孙节点（含根节点自身）。

    轻量查询：仅返回 Resource 基础字段，不预加载 latest_version 等内容。
    供资源补全模块的路径匹配使用；内容续写另行按 ID 批量加载版本内容。

    Args:
        db: 数据库会话。
        root_ids: 根节点 ID 列表（ResourceBackend 的 resource_id）。

    Returns:
        按深度优先顺序返回的节点列表，包含根节点自身。
    """
    if not root_ids:
        return []

    cte = select(
        resource_model.Resource.id,
        resource_model.Resource.parentId,
    ).where(resource_model.Resource.id.in_(root_ids)).cte(name="completion_descendants", recursive=True)

    cte = cte.union_all(
        select(
            resource_model.Resource.id,
            resource_model.Resource.parentId,
        ).join(cte, resource_model.Resource.parentId == cte.c.id)
    )

    stmt = select(cte.c.id)
    result = await db.execute(stmt)
    descendant_ids = result.scalars().all()

    if not descendant_ids:
        return []

    result = await db.execute(
        select(resource_model.Resource).where(resource_model.Resource.id.in_(descendant_ids))
    )
    return list(result.scalars().all())


async def get_editable_files(
    db: AsyncSession,
    file_ids: List[str],
) -> Dict[str, str]:
    """查询数据库直存（可写）文件的纯文本内容。

    双引擎存储约定（与 file_service 保持一致）：
    storage_type == 'db' 时文件文本存于 File.content，前端可读写；
    storage_type == 'local' 时内容在磁盘，File.content 为空，不参与补全。

    Returns:
        {file_id: content}，仅包含 storage_type == 'db' 且有文本内容的文件。
    """
    if not file_ids:
        return {}

    result = await db.execute(
        select(file_model.File.id, file_model.File.content)
        .where(
            file_model.File.id.in_(file_ids),
            file_model.File.storage_type == 'db',
        )
    )
    return {fid: content for fid, content in result.all() if content}
