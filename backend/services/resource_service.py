# backend/services/resource_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Dict, Optional
from fastapi import HTTPException

from backend.crud import resource_crud, kb_crud
from backend.models import resource_model
from backend.schemas import resource as schemas
from backend.schemas import kb as kb_schemas
from backend.schemas.enums import ResourceType, MoveAction, ResourceItemType, FileManagementType
# 复用 chat_service 中的文本截取工具，保持逻辑一致
from backend.services.chat_service import extract_context_snippet
from backend.services.kb_service import KnowledgeBaseService


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
    验证移动操作是否违反层级约束。
    主要约束: KNOWLEDGE_BASE 不能被移动到另一个 KNOWLEDGE_BASE 内部。
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

    # 2. 分析目标位置的上下文 (是否在 KB 内)
    is_target_inside_kb = False

    if target_parent_id:
        # 获取目标父节点的所有祖先
        ancestors = await resource_crud.get_batch_resource_ancestors(db, [target_parent_id])
        # 检查祖先中是否有 KB
        kb_ancestors = [res for res in ancestors if res.resourceType == ResourceType.KNOWLEDGE_BASE.value]

        if len(kb_ancestors) > 1:
            raise HTTPException(status_code=400,
                                detail="Target location is inside nested Knowledge Bases, which is invalid.")

        if len(kb_ancestors) == 1:
            is_target_inside_kb = True

    # 3. 检查每一个被移动的项目
    stmt = select(resource_model.Resource).where(resource_model.Resource.id.in_(move_request.item_ids))
    result = await db.execute(stmt)
    items = result.scalars().all()

    for item in items:
        # 规则: 如果移动的是 KNOWLEDGE_BASE，不能移入另一个 KB
        if item.resourceType == ResourceType.KNOWLEDGE_BASE.value:
            if is_target_inside_kb:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot move Knowledge Base '{item.name}' inside another Knowledge Base."
                )


async def move_resources(db: AsyncSession, move_request: schemas.ResourceMoveRequest) -> bool:
    """
    执行资源移动，并处理副作用（如递归更新 kb_id、清理向量等）。
    替代 resource_crud.move_resources 的直接调用。
    """
    # 1. 验证操作合法性
    await validate_move_operation(db, move_request)

    # 2. 确定目标位置的 KB ID
    target_kb_id = await _resolve_target_kb_id(db, move_request)

    # 3. 执行物理移动 (更新 parentId 和 sortOrder)
    success = await resource_crud.move_resources(db, move_request)
    if not success:
        return False

    # 4. 处理副作用：递归更新 kb_id 并处理向量清理
    kb_service = KnowledgeBaseService(db)

    for item_id in move_request.item_ids:
        await _process_move_side_effects(db, kb_service, item_id, target_kb_id)

    return True


async def _resolve_target_kb_id(db: AsyncSession, move_request: schemas.ResourceMoveRequest) -> Optional[str]:
    """
    解析移动目标的 KB ID。如果目标不在 KB 内，返回 None。
    """
    target_parent_id = None
    if move_request.action == MoveAction.INSIDE:
        if move_request.reference_id != "root":
            target_parent_id = move_request.reference_id
    else:
        ref_resource = await resource_crud.get_resource(db, move_request.reference_id)
        if ref_resource:
            target_parent_id = ref_resource.parentId

    if not target_parent_id:
        return None

    # 向上查找最近的 Knowledge Base
    ancestors = await resource_crud.get_batch_resource_ancestors(db, [target_parent_id])
    for res in ancestors:
        if res.resourceType == ResourceType.KNOWLEDGE_BASE.value:
            return res.id

    return None


async def _process_move_side_effects(
        db: AsyncSession,
        kb_service: KnowledgeBaseService,
        root_item_id: str,
        new_kb_id: Optional[str]
):
    """
    递归处理移动后的副作用：
    1. 查找子树中所有资源。
    2. 如果 kb_id 发生变化（移出、移入、换库），执行相应逻辑。
    """
    # 使用 CTE 递归获取所有子孙节点 (包括自身)
    cte = select(resource_model.Resource).where(resource_model.Resource.id == root_item_id).cte(name="hierarchy", recursive=True)

    # 递归部分
    child = resource_model.Resource
    cte = cte.union_all(
        select(child).join(cte, child.parentId == cte.c.id)
    )

    # 查询所有涉及的资源
    stmt = select(resource_model.Resource).join(cte, resource_model.Resource.id == cte.c.id)
    result = await db.execute(stmt)
    all_resources = result.scalars().all()

    for res in all_resources:
        # 如果是 KB 本身，跳过（KB 的 kb_id 应始终为 None，且 validate 已保证不会嵌套）
        if res.resourceType == ResourceType.KNOWLEDGE_BASE.value:
            continue

        old_kb_id = res.kb_id

        # 如果 kb_id 没有变化，跳过
        if old_kb_id == new_kb_id:
            continue

        # --- 变化处理逻辑 ---

        # 1. 如果旧环境是 KB，且现在移出或换库 -> 清理旧向量
        if old_kb_id:
            # 尝试获取旧 KB 的维度配置以清理向量
            # 注意：这里我们假设 old_kb_id 指向有效的 KB 资源
            try:
                old_kb = await resource_crud.get_resource_with_versions(db, old_kb_id)
                if old_kb and old_kb.latest_version and old_kb.latest_version.attributes:
                    dimension = old_kb.latest_version.attributes.get("dimension")
                    if dimension:
                        # 调用 Service 的内部方法清理向量
                        await kb_service._cleanup_vectors(res.id, dimension)
            except Exception:
                # 容错处理，防止因旧数据异常导致移动失败
                pass

            # 物理删除 Chunk 记录
            await kb_crud.delete_chunks_by_resource(db, res.id)

        # 2. 更新 kb_id
        res.kb_id = new_kb_id

        # 3. 如果移入新 KB (new_kb_id 不为空)
        if new_kb_id:
            # 如果是 FILE 类型且没有配置，应用默认配置
            if res.resourceType == ResourceType.FILE.value or res.resourceType == ResourceType.KB_FILE.value:
                if not res.kb_config:
                    default_config = kb_schemas.KBTextSplitterConfig(
                        splitter_type=kb_schemas.KBSplitterType.SIMPLE,
                        chunk_size=500,
                        chunk_overlap=50
                    )
                    res.kb_config = default_config.model_dump()

    # 提交更改
    await db.commit()
