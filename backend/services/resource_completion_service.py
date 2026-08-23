# backend/services/resource_completion_service.py

from collections import defaultdict
from typing import Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import agent_crud, backend_crud, resource_crud, resource_completion_crud
from backend.models import resource_model
from backend.schemas.enums import BackendType, ResourceItemType, ResourceType
from backend.services import resource_service

# 与 MamboResourceBackend._DIRECT_TEXT_TYPES 保持一致：
# 仅这些类型的 latest_version.content 是真实文本；
# FILE 类型的 content 是物理文件 ID，需按 storage_type 判定是否可写后再读取 File.content
_DIRECT_TEXT_TYPES = frozenset({
    ResourceType.SYSTEM_PROMPT.value,
    ResourceType.SUBMESSAGE_TEMPLATE.value,
})

# 续写片段截断：换行为强边界（遇即截断），其次软上限内找标点边界，最后硬截断兜底
_MIN_SNIPPET_LEN = 16
_BOUNDARY_CHARS = frozenset("。.!！?？;；,，、:：")


def _truncate_snippet(content: str, start: int, max_len: int) -> str:
    """截断续写片段。

    规则：
    1. 遇到第一个换行即截断（不含换行本身），保证建议为单行；
    2. 无换行时，在 [start+min, start+max) 内从后往前找标点边界，截断不含符号本身；
    3. 无标点边界时在 max_len 处硬截断兜底。
    """
    end = start + max_len
    if start >= len(content):
        return ""

    # 1. 换行强边界（\n 或 \r）
    newline = len(content)
    for ch in ("\n", "\r"):
        pos = content.find(ch, start)
        if 0 <= pos < newline:
            newline = pos
    if newline < end:
        return content[start:newline]

    # 2. 无换行：软上限内从后往前找标点边界
    scan_start = start + _MIN_SNIPPET_LEN
    if scan_start >= end:
        return content[start:end]

    window = content[scan_start:end]
    for i in range(len(window) - 1, -1, -1):
        if window[i] in _BOUNDARY_CHARS:
            return content[start : scan_start + i]

    # 3. 硬截断兜底
    return content[start:end]


async def resolve_agent_resource_roots(db: AsyncSession, agent_id: str) -> List[str]:
    """解析 Agent 挂载的 ResourceBackend 根节点 ID 列表。

    规则：仅统计 backendType == 'resource' 的挂载项，
    取其 configData.resource_id；指向已删除节点或非文件夹的项会被跳过。
    未挂载任何 ResourceBackend 时返回空列表（调用方据此返回 enabled=False）。
    """
    agent = await agent_crud.get_agent(db, agent_id)
    if not agent or not agent.backendIds:
        return []

    backends = await backend_crud.get_backends_by_ids(db, agent.backendIds)
    roots: List[str] = []
    for bk in backends:
        if bk.backendType != BackendType.RESOURCE.value:
            continue
        resource_id = (bk.configData or {}).get("resource_id")
        if resource_id:
            roots.append(resource_id)

    return roots


def _build_children_map(
    nodes: List[resource_model.Resource],
    node_ids: set,
) -> Dict[str, List[resource_model.Resource]]:
    """将子树节点按 parentId 分组，仅保留父节点也在子树内的连接。"""
    children: Dict[str, List[resource_model.Resource]] = defaultdict(list)
    for node in nodes:
        if node.parentId and node.parentId in node_ids:
            children[node.parentId].append(node)
    return children


def _fuzzy_match_path(
    nodes: List[resource_model.Resource],
    segments: List[str],
    trailing_slash: bool,
    children: Dict[str, List[resource_model.Resource]],
) -> List[resource_model.Resource]:
    """从根目录导航失败时的回退：在整个子树中按名称模糊匹配路径分段。"""
    if not segments:
        return []

    *parent_segs, last = segments

    if not parent_segs:
        if trailing_slash:
            matching = [
                n for n in nodes
                if n.itemType == ResourceItemType.FOLDER.value and n.name == last
            ]
            result: List[resource_model.Resource] = []
            for m in matching:
                result.extend(children.get(m.id, []))
            return result
        else:
            return [n for n in nodes if n.name.startswith(last)]

    level = [
        n for n in nodes
        if n.itemType == ResourceItemType.FOLDER.value and n.name == parent_segs[0]
    ]

    for seg in parent_segs[1:]:
        next_lvl: List[resource_model.Resource] = []
        for r in level:
            next_lvl.extend([
                c for c in children.get(r.id, [])
                if c.itemType == ResourceItemType.FOLDER.value and c.name == seg
            ])
        level = next_lvl
        if not level:
            return []

    if trailing_slash:
        matching: List[resource_model.Resource] = []
        for r in level:
            matching.extend([
                c for c in children.get(r.id, [])
                if c.itemType == ResourceItemType.FOLDER.value and c.name == last
            ])
        result: List[resource_model.Resource] = []
        for m in matching:
            result.extend(children.get(m.id, []))
        return result
    else:
        result: List[resource_model.Resource] = []
        for r in level:
            result.extend([
                c for c in children.get(r.id, [])
                if c.name.startswith(last)
            ])
        return result


async def complete_path(
    db: AsyncSession,
    agent_id: str,
    prefix: str,
    limit: int,
) -> Tuple[bool, List[dict]]:
    """路径补全：按 '/' 分段匹配挂载子树，返回最后一段的直接子节点。"""
    roots = await resolve_agent_resource_roots(db, agent_id)
    if not roots:
        return False, []

    nodes = await resource_completion_crud.get_descendants_brief(db, roots)
    if not nodes:
        return False, []

    root_id_set = set(roots)
    valid_roots = [n for n in nodes if n.id in root_id_set and n.itemType == ResourceItemType.FOLDER.value]
    if not valid_roots:
        return False, []

    children = _build_children_map(nodes, {n.id for n in nodes})

    segments = [s for s in prefix.split("/") if s]
    trailing_slash = prefix.endswith("/")

    level = valid_roots
    candidates: List[resource_model.Resource] = []

    if segments:
        for seg in segments[:-1]:
            level = [
                c for r in level for c in children[r.id]
                if c.itemType == ResourceItemType.FOLDER.value and c.name == seg
            ]
            if not level:
                break

        if level:
            last = segments[-1]
            if trailing_slash:
                level = [
                    c for r in level for c in children[r.id]
                    if c.itemType == ResourceItemType.FOLDER.value and c.name == last
                ]
                candidates = [c for r in level for c in children[r.id]]
            else:
                candidates = [
                    c for r in level for c in children[r.id]
                    if c.name.startswith(last)
                ]

        if not candidates:
            candidates = _fuzzy_match_path(nodes, segments, trailing_slash, children)
    else:
        candidates = [c for r in level for c in children[r.id]]

    candidates.sort(key=lambda n: (n.itemType != ResourceItemType.FOLDER.value, n.sortOrder))
    candidates = candidates[:limit]

    if not candidates:
        return True, []

    paths = await resource_service.build_resource_paths(db, [c.id for c in candidates])

    items = [
        {
            "name": c.name,
            "item_type": c.itemType,
            "resource_type": c.resourceType,
            "path": paths.get(c.id, ""),
            "is_dir": c.itemType == ResourceItemType.FOLDER.value,
        }
        for c in candidates
    ]
    return True, items


async def complete_content(
    db: AsyncSession,
    agent_id: str,
    prefix: str,
    limit: int,
    max_items: int,
) -> Tuple[bool, List[dict]]:
    """内容续写：在挂载子树内检索资源内容中前缀之后的续写片段。

    内容来源按资源类型分派：
    - system_prompt / submessage_template：latest_version.content（直接文本）
    - file：仅 storage_type == 'db' 的可写文件（File.content 为真实文本），
      不可写文件内容在磁盘，不参与补全
    - 其他类型（kb_file / skill 文件等 content 为文件 ID 的）跳过
    """
    roots = await resolve_agent_resource_roots(db, agent_id)
    if not roots:
        return False, []

    nodes = await resource_completion_crud.get_descendants_brief(db, roots)
    if not nodes:
        return False, []

    text_nodes = [
        n for n in nodes
        if n.itemType == ResourceItemType.RESOURCE.value
        and n.resourceType in _DIRECT_TEXT_TYPES
    ]
    file_nodes = [
        n for n in nodes
        if n.itemType == ResourceItemType.RESOURCE.value
        and n.resourceType == ResourceType.FILE.value
    ]
    if not text_nodes and not file_nodes:
        return True, []

    # 组装 (resource_id, content) 候选
    candidates: List[Tuple[str, str]] = []

    if text_nodes:
        resources = await resource_crud.get_resources_by_ids(db, [n.id for n in text_nodes])
        for res in resources:
            if res.latest_version and res.latest_version.content:
                candidates.append((res.id, res.latest_version.content))

    if file_nodes:
        resources = await resource_crud.get_resources_by_ids(db, [n.id for n in file_nodes])
        file_ids = [
            res.latest_version.content
            for res in resources
            if res.latest_version and res.latest_version.content
        ]
        editable_contents = await resource_completion_crud.get_editable_files(db, file_ids)
        for res in resources:
            if res.latest_version and res.latest_version.content:
                content = editable_contents.get(res.latest_version.content)
                if content:
                    candidates.append((res.id, content))

    low_prefix = prefix.lower()
    items: List[dict] = []
    for resource_id, content in candidates:
        idx = content.lower().find(low_prefix)
        if idx < 0:
            continue
        start = idx + len(prefix)
        items.append(
            {
                "resource_id": resource_id,
                "snippet": _truncate_snippet(content, start, limit),
            }
        )
        if len(items) >= max_items:
            break

    if not items:
        return True, []

    paths = await resource_service.build_resource_paths(db, [i["resource_id"] for i in items])
    for item in items:
        item["resource_path"] = paths.get(item["resource_id"], "")

    return True, items
