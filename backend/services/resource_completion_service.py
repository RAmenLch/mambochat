# backend/services/resource_completion_service.py

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from mambo_agents.backends.schemas import VirtualPath

from backend.crud import agent_crud, backend_crud, resource_crud, resource_completion_crud
from backend.models import resource_model
from backend.schemas.enums import BackendType, ResourceItemType, ResourceType
from backend.services import resource_service

logger = logging.getLogger(__name__)

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


# =====================================================================
# Local / SSH / Api：逐级路径补全（实例缓存 + 目录缓存 + 子文件夹预热）
# =====================================================================

# 可参与路径补全的"文件系统型" backend 类型（resource 走 DB 资源树，不在此列）
_FS_BACKEND_TYPES = frozenset({
    BackendType.LOCAL.value,
    BackendType.SSH.value,
    BackendType.API.value,
})

_FS_LS_TIMEOUT = 3.0        # 单次 ls 超时（秒）：慢网络/断连兜底，超时按空候选处理
_PREWARM_MAX_FOLDERS = 8    # 每次最多预热的子文件夹数（按排序靠前优先）
_PREWARM_CONCURRENCY = 2    # 同时进行的预热任务数（SSH als 内部串行，必须限流）
_PREWARM_TIMEOUT = 2.0      # 单个预热 ls 超时（秒）
_DIR_CACHE_TTL = 60.0       # 目录列表缓存 TTL（秒）：输入场景足够，避免文件系统变化长期失真
_INSTANCE_TTL = 600.0       # backend 实例缓存 TTL（秒）
_INSTANCE_MAX = 32          # 实例缓存容量上限（超出按 FIFO 淘汰最旧）


class BackendInstanceCache:
    """Backend 实例缓存：TTL 懒失效 + in-flight 构建去重 + 失败自愈。

    补全是高频接口（250ms 防抖），而 SSH 实例构建需同步连接（0.5~2s），
    绝不能每次请求重建。构建失败不缓存，下次请求重试；调用方发现
    backend 失活时调用 invalidate 主动销毁（断线自愈）。
    """

    def __init__(self, ttl: float = _INSTANCE_TTL, max_size: int = _INSTANCE_MAX):
        self._ttl = ttl
        self._max_size = max_size
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._order: List[str] = []
        self._inflight: Dict[str, asyncio.Task] = {}

    async def get_or_build(self, key: str, builder: Callable[[], Any]) -> Any:
        """获取实例；未命中或过期时构建（并发请求共享同一次构建）。"""
        entry = self._store.get(key)
        if entry and time.monotonic() - entry[0] < self._ttl:
            return entry[1]

        task = self._inflight.get(key)
        if task is not None:
            return await task

        async def _build() -> Any:
            try:
                instance = await builder()
                if instance is None:
                    return None
                self._store[key] = (time.monotonic(), instance)
                self._order.append(key)
                if len(self._order) > self._max_size:
                    old = self._order.pop(0)
                    self._store.pop(old, None)
                return instance
            finally:
                self._inflight.pop(key, None)

        task = asyncio.create_task(_build())
        self._inflight[key] = task
        return await task

    def invalidate(self, key: str) -> None:
        """销毁实例（如 ls 持续失败判定 backend 失活），下次请求重建。"""
        self._store.pop(key, None)
        if key in self._order:
            self._order.remove(key)


_instance_cache = BackendInstanceCache()


class DirListCache:
    """目录列表缓存：key=(agent_id, 虚拟路径) → ls 结果。

    预热与实时补全共用同一份缓存：实时 ls 回填，预热后台填充，
    后续输入直接命中，省掉一次网络 RTT。
    """

    def __init__(self, ttl: float = _DIR_CACHE_TTL):
        self._ttl = ttl
        self._store: Dict[Tuple[str, str], Tuple[float, List[Any]]] = {}

    def get(self, agent_id: str, vpath: str) -> Optional[List[Any]]:
        entry = self._store.get((agent_id, vpath))
        if entry and time.monotonic() - entry[0] < self._ttl:
            return entry[1]
        return None

    def set(self, agent_id: str, vpath: str, entries: List[Any]) -> None:
        self._store[(agent_id, vpath)] = (time.monotonic(), entries)


_dir_cache = DirListCache()


class PrewarmScheduler:
    """后台预热：对已列举目录的直接子文件夹提前 ls 并写入目录缓存。

    fire-and-forget：任何失败只记日志，绝不影响补全主流程。
    仅 ssh/api 类型启用（网络 RTT 收益最大；Local 本地 ls 亚毫秒级无需预热）。
    """

    def __init__(
        self,
        max_folders: int = _PREWARM_MAX_FOLDERS,
        concurrency: int = _PREWARM_CONCURRENCY,
    ):
        self._max_folders = max_folders
        self._sem = asyncio.Semaphore(concurrency)

    def schedule(self, agent_id: str, backend: Any, folders: List[Any]) -> None:
        try:
            asyncio.get_running_loop().create_task(self._run(agent_id, backend, folders))
        except RuntimeError:
            pass  # 无运行中事件循环（极端场景）直接丢弃

    async def _run(self, agent_id: str, backend: Any, folders: List[Any]) -> None:
        for folder in folders[: self._max_folders]:
            vpath = folder.path.value
            if _dir_cache.get(agent_id, vpath) is not None:
                continue
            async with self._sem:
                try:
                    result = await asyncio.wait_for(
                        backend.als(folder.path), timeout=_PREWARM_TIMEOUT
                    )
                    if result.error is None:
                        _dir_cache.set(agent_id, vpath, result.entries or [])
                except Exception as e:
                    logger.debug("[completion] prewarm %s failed: %s", vpath, e)


_prewarmer = PrewarmScheduler()


async def _resolve_real_backend_type(
    db: AsyncSession, agent_id: str
) -> Optional[str]:
    """解析 real backend 类型（default_backend_id 优先，否则第一个挂载）。

    与图构建的 _resolve_real_backend_id 规则保持一致。仅返回
    local/ssh/api 类型；resource / 无挂载返回 None（调用方据此走 DB 逻辑）。
    """
    agent = await agent_crud.get_agent(db, agent_id)
    if not agent or not agent.backendIds:
        return None
    backends = await backend_crud.get_backends_by_ids(db, agent.backendIds)
    if not backends:
        return None

    chosen = None
    if agent.defaultBackendId:
        for bk in backends:
            if bk.id == agent.defaultBackendId:
                chosen = bk
                break
    if chosen is None:
        chosen = backends[0]
    b_type = getattr(chosen, "backendType", None)
    return b_type if b_type in _FS_BACKEND_TYPES else None


async def _get_fs_backend(
    db: AsyncSession, agent_id: str
) -> Tuple[Optional[str], Optional[Any], Optional[str]]:
    """获取补全用的 HybridWorkspaceBackend 实例（带缓存）。

    构建完整 Hybrid（real backend + skills/memory + 其余挂载 backend），
    使补全同时覆盖 /workspace（real）与 /.mambo/{name}（虚拟空间）路径，
    路径路由由 HybridWorkspaceBackend.als 内部完成。

    Returns:
        (cache_key, backend, real_backend_type)；real backend 非
        local/ssh/api 或无挂载时返回 (None, None, None)。
    """
    agent = await agent_crud.get_agent(db, agent_id)
    if not agent or not agent.backendIds:
        return None, None, None

    from backend.services.generation.agent.backend_factory import (
        build_mounted_backends,
        build_skill_resource_roots,
    )
    from backend.services.generation.core.llm_io import AgentConfig
    from backend.services.generation.graph_builders.mambo_agent_builder import (
        _build_any_backend,
        _build_mambo_backend,
        _make_session_factory,
        _resolve_real_backend_id,
    )
    from backend.store import get_store

    mounted = await build_mounted_backends(db, agent)
    if not mounted:
        return None, None, None

    real_id = _resolve_real_backend_id(mounted, agent.defaultBackendId)
    real_mb = next((m for m in mounted if m.get("id") == real_id), None)
    if not real_mb:
        return None, None, None

    # resource real 也构建 Hybrid（用于 /workspace、/.mambo 虚拟路径补全）；
    # 相对路径补全仍由 complete_path 分流到 DB 全子树逻辑，保留"从中间补"
    b_type = real_mb.get("backendType")
    cache_key = f"{agent_id}|{real_id}"

    async def _build_hybrid() -> Optional[Any]:
        """构建完整 Hybrid（支持 /workspace + /.mambo）。失败返回 None。"""
        try:
            skill_roots = await build_skill_resource_roots(db, agent)
            agent_config = AgentConfig(
                mounted_backends=mounted,
                default_backend_id=agent.defaultBackendId,
                skill_resource_roots=skill_roots or None,
                memory_resource_roots=None,
            )
            store = get_store()
            # SSH 连接等慢操作在线程中执行，避免阻塞事件循环
            return await asyncio.wait_for(
                asyncio.to_thread(_build_mambo_backend, agent_config, store=store),
                timeout=8.0,
            )
        except Exception as e:
            # 任一挂载 backend 构建失败（如 SSH 连不上）不得拖垮补全
            logger.warning("[completion] hybrid build failed, fallback to real-only: %s", e)
            return None

    async def _build_real_only() -> Optional[Any]:
        """降级：仅构建 real backend（保证 /workspace 补全）。失败返回 None。"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _build_any_backend, real_mb, _make_session_factory()
                ),
                timeout=8.0,
            )
        except Exception as e:
            logger.warning("[completion] real backend build failed: %s", e)
            return None

    async def builder() -> Any:
        hybrid = await _build_hybrid()
        if hybrid is not None:
            return hybrid
        return await _build_real_only()

    backend = await _instance_cache.get_or_build(cache_key, builder)
    if backend is None:
        return None, None, None
    return cache_key, backend, b_type


async def _fs_ls(
    agent_id: str, backend: Any, vpath: VirtualPath
) -> Optional[List[Any]]:
    """带目录缓存 + 超时 + 异常兜底的 ls；失败返回 None（调用方按空候选处理）。"""
    cached = _dir_cache.get(agent_id, vpath.value)
    if cached is not None:
        return cached
    try:
        result = await asyncio.wait_for(backend.als(vpath), timeout=_FS_LS_TIMEOUT)
    except Exception as e:
        logger.warning("[completion] ls %s failed: %s", vpath.value, e)
        return None
    if result.error is not None:
        logger.warning("[completion] ls %s error: %s", vpath.value, result.error.message)
        return None
    entries = result.entries or []
    _dir_cache.set(agent_id, vpath.value, entries)
    return entries


async def complete_fs_path(
    db: AsyncSession,
    agent_id: str,
    prefix: str,
    limit: int,
    cache_key: str,
    backend: Any,
    b_type: str,
) -> Tuple[bool, List[dict]]:
    """Hybrid 逐级路径补全：按 '/' 分段逐级 ls。

    backend 为 HybridWorkspaceBackend，路径路由由它内部完成：
    - 前缀以 /.mambo 开头 → 起点 /.mambo（可进入 skills/memory/挂载 backend 虚拟空间）
    - 其他（含空）→ 起点 real backend 的 workspace_root（默认 /workspace）

    与 Resource 的"全子树 + 模糊回退"不同：严格逐级导航，任一级
    不存在即返回空。任何异常/超时都安静降级为空候选，不影响输入。
    """
    try:
        if prefix == "/.mambo" or prefix.startswith("/.mambo/"):
            root = "/.mambo"
        else:
            root = backend.workspace_root.value

        # 虚拟根路径补全：输入 "/"、"/.m"、"/w" 等根前缀时提示根目录本身
        # （Hybrid 有 /workspace + /.mambo 两个根；降级 real-only 只有 workspace_root）
        if prefix.startswith("/") and not prefix.startswith(root) and not prefix.startswith("/.mambo"):
            from mambo_agents.backends.hybrid_workspace import HybridWorkspaceBackend
            is_hybrid = isinstance(backend, HybridWorkspaceBackend)
            seg = prefix.lstrip("/")
            roots = ["/.mambo", root] if is_hybrid else [root]
            matches = [r for r in roots if r.lstrip("/").startswith(seg)]
            items = [
                {
                    "name": r.lstrip("/"),
                    "item_type": "folder",
                    "resource_type": None,
                    "path": "/",
                    "is_dir": True,
                }
                for r in matches
            ]
            return True, items[:limit]

        # 输入以 root 开头时剥掉前缀（如 "/workspace/src" → "src"），
        # 使"输入根路径本身"（"/workspace"、"/.mambo"）正确列出根全部内容
        rel = prefix[len(root):] if prefix.startswith(root) else prefix
        segments = [s for s in rel.split("/") if s]
        trailing_slash = rel.endswith("/")

        if trailing_slash:
            nav = segments
            filter_prefix: Optional[str] = None
        else:
            nav = segments[:-1]
            filter_prefix = segments[-1] if segments else None

        target = VirtualPath(root)
        for seg in nav:
            target = target.join(seg)
            entries = await _fs_ls(agent_id, backend, target)
            if entries is None:
                return True, []  # 目录不存在/不可达 → 无候选（enabled=True 表示支持补全）

        entries = await _fs_ls(agent_id, backend, target)
        if entries is None:
            return True, []

        if filter_prefix is not None:
            entries = [e for e in entries if e.path.name.startswith(filter_prefix)]

        entries.sort(key=lambda e: (not e.is_dir, e.path.name.lower()))
        entries = entries[:limit]

        items = [
            {
                "name": e.path.name,
                "item_type": "folder" if e.is_dir else "resource",
                "resource_type": None,
                "path": target.value,
                "is_dir": e.is_dir,
            }
            for e in entries
        ]

        # 预热：仅 ssh/api（网络 RTT 收益最大）
        if b_type in (BackendType.SSH.value, BackendType.API.value):
            folders = [e for e in entries if e.is_dir]
            _prewarmer.schedule(agent_id, backend, folders)

        return True, items
    except Exception as e:
        logger.warning("[completion] complete_fs_path failed: %s", e)
        # backend 异常（如 SSH 断连）→ 销毁实例，下次请求自愈重建
        _instance_cache.invalidate(cache_key)
        return False, []


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
    """路径补全：按 Agent 的 real backend 类型 + 前缀形式分派。

    - 虚拟路径前缀（以 '/' 开头，如 /workspace、/.m、/.mambo/...）→
      Hybrid 逐级 ls 补全（complete_fs_path），resource real 同样支持
    - 相对路径（如 foo/bar）：
      - local / ssh / api real → Hybrid 逐级 ls
      - resource real → DB 全子树补全（保留"从中间补"的模糊回退能力）
    """
    try:
        cache_key, backend, b_type = await _get_fs_backend(db, agent_id)
    except Exception as e:
        # 最外层兜底：backend 解析任何异常都安静降级，绝不 500
        logger.warning("[completion] resolve fs backend failed: %s", e)
        cache_key, backend, b_type = None, None, None
    if backend is not None and (
        prefix.startswith("/") or b_type != BackendType.RESOURCE.value
    ):
        return await complete_fs_path(
            db, agent_id, prefix, limit, cache_key, backend, b_type
        )

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

    local / ssh / api 类型快速短路（不构建 backend 实例、不查资源树），
    返回 enabled=False，前端自然无内容候选。
    """
    try:
        if await _resolve_real_backend_type(db, agent_id) is not None:
            return False, []
    except Exception as e:
        logger.warning("[completion] resolve backend type failed: %s", e)

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
