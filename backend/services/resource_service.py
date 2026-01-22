# backend/services/resource_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Optional
from fastapi import HTTPException

from backend.crud import resource_crud
from backend.models import resource_model
from backend.schemas import resource as schemas
from backend.schemas.enums import ResourceType, MoveAction, ResourceItemType
# 复用 chat_service 中的文本截取工具，保持逻辑一致
from backend.services.chat_service import extract_context_snippet


async def build_resource_paths(db: AsyncSession, resource_ids: List[str]) -> Dict[str, str]:
    """
    批量构建资源的路径字符串（例如：Folder A / Folder B）。
    返回字典: {resource_id: path_string}
    路径不包含资源节点自身，仅表示其所在的目录层级。
    """
    if not resource_ids:
        return {}

    # 获取所有相关的祖先节点（包括自身）
    rows = await resource_crud.get_batch_resource_ancestors(db, resource_ids)

    # 构建节点查找表: id -> {name, parentId}
    node_map = {row.id: {"name": row.name, "parentId": row.parentId} for row in rows}

    paths = {}
    for start_id in resource_ids:
        if start_id not in node_map:
            continue

        current_id = start_id
        path_segments = []

        # 向上遍历直到根节点
        while current_id:
            node = node_map.get(current_id)
            if not node:
                break
            path_segments.append(node["name"])
            current_id = node["parentId"]

        # 移除自身节点（路径通常指父级目录结构，不包含文件自身）
        if path_segments:
            path_segments.pop(0)

        # 反转列表并拼接，形成 Root / Folder / ...
        paths[start_id] = " / ".join(reversed(path_segments))

    return paths


async def validate_move_operation(db: AsyncSession, move_request: schemas.ResourceMoveRequest):
    """
    验证移动操作是否违反知识库的层级约束。
    约束 1: KNOWLEDGE_BASE 不能被移动到另一个 KNOWLEDGE_BASE 内部（无论嵌套多少层）。
    约束 2: KB_FILE 不能被移动到 KNOWLEDGE_BASE 外部。
    约束 3: KB_FILE 不能跨 KNOWLEDGE_BASE 移动 (即只能在同一个 KB 内调整文件夹，不能换库)。
    """
    if not move_request.item_ids:
        return

    # 1. 确定目标父节点 ID
    target_parent_id = None
    if move_request.action == MoveAction.INSIDE:
        if move_request.reference_id != "root":
            target_parent_id = move_request.reference_id
    else:
        # Before / After
        if move_request.reference_id == "root":
            # 根节点无法作为 sibling 操作的参考
            raise HTTPException(status_code=400, detail="Cannot move relative to root.")
        ref_resource = await resource_crud.get_resource(db, move_request.reference_id)
        if not ref_resource:
            raise HTTPException(status_code=404, detail="Reference resource not found.")
        target_parent_id = ref_resource.parentId

    # 2. 分析目标位置的上下文 (是否在 KB 内，KB ID 是多少)
    target_kb_id = None
    is_target_inside_kb = False

    if target_parent_id:
        # 获取目标父节点的所有祖先
        ancestors = await resource_crud.get_batch_resource_ancestors(db, [target_parent_id])
        # 检查祖先中是否有 KB
        kb_ancestors = [res for res in ancestors if res.resourceType == ResourceType.KNOWLEDGE_BASE.value]

        if len(kb_ancestors) > 1:
            # 这种情况理论上不应存在（如果之前约束严格），但为了安全
            raise HTTPException(status_code=400,
                                detail="Target location is inside nested Knowledge Bases, which is invalid.")

        if len(kb_ancestors) == 1:
            is_target_inside_kb = True
            target_kb_id = kb_ancestors[0].id

    # 3. 检查每一个被移动的项目
    # --- 修复开始: 使用 select 直接查询，替代不存在的 crud 方法 ---
    stmt = select(resource_model.Resource).where(resource_model.Resource.id.in_(move_request.item_ids))
    result = await db.execute(stmt)
    items = result.scalars().all()
    # --- 修复结束 ---

    for item in items:
        # 规则 A: 如果移动的是 KNOWLEDGE_BASE
        if item.resourceType == ResourceType.KNOWLEDGE_BASE.value:
            if is_target_inside_kb:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot move Knowledge Base '{item.name}' inside another Knowledge Base."
                )

        # 规则 B: 如果移动的是 KB_FILE
        elif item.resourceType == ResourceType.KB_FILE.value:
            if not is_target_inside_kb:
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{item.name}' belongs to a Knowledge Base and cannot be moved outside."
                )

            # 检查是否跨库
            # 获取该 item 当前所在的 KB
            current_ancestors = await resource_crud.get_batch_resource_ancestors(db,
                                                                                 [item.parentId]) if item.parentId else []
            current_kb = next(
                (res for res in current_ancestors if res.resourceType == ResourceType.KNOWLEDGE_BASE.value), None)

            # 如果当前就在 KB 里，且目标 KB ID 不同，则禁止移动
            if current_kb and current_kb.id != target_kb_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{item.name}' cannot be moved to a different Knowledge Base."
                )

        # 规则 C: 如果移动的是普通 FOLDER
        elif item.itemType == ResourceItemType.FOLDER.value:
            # 获取当前位置上下文
            current_ancestors = await resource_crud.get_batch_resource_ancestors(db,
                                                                                 [item.parentId]) if item.parentId else []
            is_currently_inside_kb = any(
                res.resourceType == ResourceType.KNOWLEDGE_BASE.value for res in current_ancestors)

            if is_currently_inside_kb and not is_target_inside_kb:
                # 尝试从 KB 移出
                # 严格模式：禁止文件夹移出 KB，防止带走下面的 KB_FILE
                raise HTTPException(
                    status_code=400,
                    detail=f"Folder '{item.name}' is inside a Knowledge Base and cannot be moved outside."
                )

            # 其他情况（如从外部移入 KB，或在 KB 内部移动）暂时允许
            pass
