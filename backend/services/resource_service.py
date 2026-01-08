# backend/services/resource_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict

from backend.crud import resource_crud
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
