"""MamboChat Agent 导出包（.mamboagent）的导出与导入服务。

实现 doc/agent-package-spec.md：
- AgentPackageExporter：Agent 闭包 + Backend 闭包 + 资源闭包（最小树/目标结构）+
  Provider 闭包 + MCP 闭包 + blob 闭包，序列化为 gzip JSON。
- AgentPackageImporter：解析/预检（dry-run）/正式导入/会话记录/清理。
"""

import base64
import gzip
import json
import re
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from backend.config.timezone_config import get_configured_now
from backend._version import __version__
from backend.crud import agent_crud, backend_crud, mcp_crud, provider_crud, resource_crud
from backend.crud import file_crud
from backend.exceptions import AppHTTPException
from backend.models import agent_model, backend_model, provider_model, resource_model
from backend.models.base_model import generate_uuid
from backend.schemas import agent as agent_schemas
from backend.schemas import kb as kb_schemas
from backend.schemas import mcp as mcp_schemas
from backend.schemas import resource as resource_schemas
from backend.schemas.agent_package import (
    AgentPackage,
    CleanupReport,
    CreatedEntity,
    ImportPreviewResponse,
    ImportReport,
    PackageAgent,
    PackageBackend,
    PackageBlob,
    PackageFileRef,
    PackageMcpServer,
    PackageModel,
    PackageProvider,
    PackageResource,
    PackageResourceVersion,
    ProviderBrief,
    RenameSuggestion,
    ResourcePreviewNode,
)
from backend.schemas.enums import (
    AgentItemType,
    BackendType,
    FileManagementType,
    ResourceItemType,
    ResourceType,
)
from backend.services.file_service import FileService
from backend.services.kb_service import KnowledgeBaseService
from backend.utils.path_safe import validate_path_safe_name

# ─────────────────────────── 常量 ───────────────────────────

FORMAT = "mambochat.agent-package"
SUPPORTED_FORMAT_VERSION = "1.3.0"
MAMBOCHAT_VERSION = __version__
SCHEMA_REF = "./agent_package_schema_v1.json"

MAX_PACKAGE_FILE_SIZE = 100 * 1024 * 1024        # 100 MB：包文件本身
MAX_TOTAL_DECODED_SIZE = 500 * 1024 * 1024       # 500 MB：解码后总内容
MAX_SINGLE_BLOB_SIZE = 20 * 1024 * 1024          # 20 MB：单个 blob

API_KEY_PLACEHOLDER = "********"
SUBAGENT_FOLDER_SUFFIX = "_subagent"
MAX_NAME_LEN = 100

# 虚拟容器固定名（§6.4 保留名；kb / skill 为单数，不与用户创建资源的保留字限制冲突）
_FIXED_CONTAINERS = ("kb", "skill", "prompt", "memory")

# Placement 种类
_KIND_KB_ROOT = "kb_root"
_KIND_SKILL_ROOT = "skill_root"
_KIND_LEAF = "leaf"
_KIND_BACKEND_FOLDER = "backend_folder"
_KIND_MEMBER = "subtree_member"

_FILE_LIKE_TYPES = frozenset({
    ResourceType.FILE.value,
    ResourceType.KB_FILE.value,
})
_LEAF_TYPES = frozenset({
    ResourceType.FILE.value,
    ResourceType.SYSTEM_PROMPT.value,
    ResourceType.SUBMESSAGE_TEMPLATE.value,
})


def _version_tuple(v: str) -> Tuple[int, ...]:
    parts = []
    for seg in str(v).split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _check_illegal_chars(name: str, label: str):
    """仅校验非法字符（不查保留字），用于规范常量容器名与 RB_ 前缀名（§6.4 前缀隔离）。"""
    if not name or not name.strip():
        raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_NAME_EMPTY", detail=f"{label} 不能为空")
    if re.search(r"[/\\\x00-\x1f\x7f]", name):
        raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_NAME_ILLEGAL_CHARS", detail=f"{label} '{name}' 包含非法字符")
    if name in (".", ".."):
        raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_NAME_DOT", detail=f'{label} 不能为 "." 或 ".."')


# ─────────────────────────── 内部数据结构 ───────────────────────────

class _Space:
    """Agent 资源命名空间（§6.4）"""
    __slots__ = ("agent_id", "agent_name", "parent", "children")

    def __init__(self, agent_id: str, agent_name: str, parent: Optional["_Space"] = None):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.parent = parent
        self.children: List["_Space"] = []


class _Placement:
    """一份真实资源的最终归属"""
    __slots__ = ("resource", "space", "kind", "container_key", "package_parent",
                 "package_id", "kb_id", "kb_config")

    def __init__(self, resource, space: _Space, kind: str, container_key: Optional[str]):
        self.resource = resource
        self.space = space
        self.kind = kind
        self.container_key = container_key
        self.package_parent: Optional[str] = None
        self.package_id: str = resource.id
        self.kb_id: Optional[str] = None
        self.kb_config: Optional[Dict[str, Any]] = None


class _VNode:
    """导出端虚拟容器节点（导入端创建为普通 folder，§6.3）"""
    __slots__ = ("package_id", "name", "parent_id", "sort_order")

    def __init__(self, name: str, parent_id: Optional[str], sort_order: int = 0):
        self.package_id = str(uuid.uuid4())
        self.name = name
        self.parent_id = parent_id
        self.sort_order = sort_order


class ImportSession:
    """单次正式导入的会话记录（内存态，重启失效，§7.4）"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created: List[CreatedEntity] = []
        self.blob_file_map: Dict[str, str] = {}   # blobId -> 新建 File 记录 id

    def add(self, entity_type: str, source_id: str, new_id: str):
        self.created.append(CreatedEntity(entity_type=entity_type, source_id=source_id, new_id=new_id))


_IMPORT_SESSIONS: Dict[str, ImportSession] = {}


class _RenamePlan:
    """冲突改名结果（§7.2）"""

    def __init__(self):
        self.main_source_id: str = ""
        self.main_agent_name: str = ""
        self.namespace_name: Optional[str] = None      # 主 Agent 资源命名空间容器名
        self.subagent_folder_name: Optional[str] = None
        self.providers: Dict[str, str] = {}            # sourceId -> new_name
        self.backends: Dict[str, str] = {}             # sourceId -> new_name
        self.suggestions: List[RenameSuggestion] = []
        self.main_agent_renamed: bool = False


# ═══════════════════════════════════════════════════════════════
# 导出器
# ═══════════════════════════════════════════════════════════════

class AgentPackageExporter:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    # ── 入口 ──
    async def export(self, agent_id: str) -> Tuple[bytes, str]:
        main_agent = await agent_crud.get_agent(self.db, agent_id)
        if main_agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if main_agent.itemType != AgentItemType.AGENT.value:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_EXPORT_NOT_AGENT", detail="只能导出 Agent，不能导出文件夹")

        agent_closure = await self._agent_closure(main_agent)

        # Backend 闭包 + Agent 字段清洗（§6.2 / §5.6）：resource / local 可导出，ssh / api 不导出
        export_backends, cleaned_backend_ids, cleaned_default_ids = await self._backend_closure(agent_closure)
        for bk in export_backends:
            _check_illegal_chars(bk.name, "Backend 名")  # RB_ 前缀隔离保留字（§6.4），仅查非法字符

        # 资源闭包（最小树 + 目标结构，§6.3/§6.4/§6.7）
        res_ctx = await self._build_resource_closure(main_agent, agent_closure, export_backends)

        # blob 闭包（§4.3/§6.8）：文件型版本内容 + 头像，按 File 记录去重
        blob_ctx = await self._build_blob_closure(res_ctx, agent_closure)

        # Provider 闭包（§6.6）
        providers_pkg = await self._build_providers(agent_closure, res_ctx.kb_roots)

        # MCP 闭包（§6.8 / §5.5）
        mcp_pkg = await self._build_mcp(agent_closure)

        agents_pkg = [
            PackageAgent(
                sourceId=a.id,
                name=a.name,
                description=a.description,
                itemType=a.itemType,
                AgentType=a.AgentType,
                systemPrompt=a.systemPrompt,
                modelParameters=a.modelParameters,
                agentParameters=a.agentParameters,
                aiModelId=a.aiModelId,
                agentAvatarId=a.agentAvatarId,
                resourcePromptList=a.resourcePromptList or [],
                enabledMcpIds=a.enabledMcpIds or [],
                subAgents=a.subAgents or [],
                backendIds=cleaned_backend_ids.get(a.id, []),
                defaultBackendId=cleaned_default_ids.get(a.id),
            )
            for a in agent_closure
        ]

        resources_pkg = self._serialize_resources(res_ctx, blob_ctx)

        backends_pkg = [
            PackageBackend(
                sourceId=b.id,
                name=b.name,
                description=b.description,
                backendType=b.backendType,
                configData=b.configData,
                tools_config=b.tools_config,
            )
            for b in export_backends
        ]

        blobs_pkg = [
            PackageBlob(
                blobId=fid,
                filename=blob_ctx.file_map[fid].filename,
                mimeType=blob_ctx.file_map[fid].mime_type,
                size=len(data),
                encoding="base64",
                data=base64.b64encode(data).decode("ascii"),
            )
            for fid, data in blob_ctx.data.items()
        ]

        pkg = AgentPackage(
            schema_ref=SCHEMA_REF,
            format=FORMAT,
            formatVersion=SUPPORTED_FORMAT_VERSION,
            mambochatVersion=MAMBOCHAT_VERSION,
            exportedAt=get_configured_now(),
            description=f"Agent '{main_agent.name}' 导出包",
            agents=agents_pkg,
            providers=providers_pkg,
            resources=resources_pkg,
            mcpServers=mcp_pkg,
            backends=backends_pkg,
            blobs=blobs_pkg,
        )

        payload = pkg.model_dump_json(by_alias=True).encode("utf-8")
        return gzip.compress(payload), main_agent.name

    # ── Agent 闭包（§6.1）──
    async def _agent_closure(self, main_agent) -> List[agent_model.Agent]:
        closure: List[agent_model.Agent] = [main_agent]
        seen = {main_agent.id}
        queue = deque([main_agent])
        while queue:
            current = queue.popleft()
            for sub_id in (current.subAgents or []):
                if sub_id in seen:
                    continue
                sub = await agent_crud.get_agent(self.db, sub_id)
                if sub is None:
                    continue  # 悬空引用照常导出（§6.8），不加入闭包
                if sub.itemType != AgentItemType.AGENT.value:
                    continue  # subAgents 仅引用 agent 节点（§5.2）
                seen.add(sub_id)
                closure.append(sub)
                queue.append(sub)
        return closure

    # ── Backend 闭包 + Agent 字段清洗（§6.2 / §5.6）──
    async def _backend_closure(
        self, agent_closure: List[agent_model.Agent]
    ) -> Tuple[List, Dict[str, List[str]], Dict[str, Optional[str]]]:
        all_ids = set()
        for a in agent_closure:
            all_ids.update(a.backendIds or [])
        backends = await backend_crud.get_backends_by_ids(self.db, list(all_ids))
        export_backends = [b for b in backends
                           if b.backendType in (BackendType.RESOURCE.value, BackendType.LOCAL.value)]
        export_backend_ids = {b.id for b in export_backends}

        cleaned_backend_ids: Dict[str, List[str]] = {}
        cleaned_default_ids: Dict[str, Optional[str]] = {}
        for a in agent_closure:
            keep = [bid for bid in (a.backendIds or []) if bid in export_backend_ids]
            cleaned_backend_ids[a.id] = keep
            default = a.defaultBackendId
            cleaned_default_ids[a.id] = default if default in export_backend_ids else None

        return export_backends, cleaned_backend_ids, cleaned_default_ids

    # ── 资源闭包（§6.3/§6.4/§6.5/§6.7）──
    async def _build_resource_closure(self, main_agent, agent_closure, export_backends):
        # 1. 空间树
        spaces: Dict[str, _Space] = {}
        for i, a in enumerate(agent_closure):
            spaces[a.id] = _Space(a.id, a.name)
        for a in agent_closure:
            sp = spaces[a.id]
            for sid in (a.subAgents or []):
                child = spaces.get(sid)
                if child:
                    sp.children.append(child)
                    child.parent = sp

        # 2. Backend 按 Agent 归类（仅 resource 类型产生挂载；local 不挂载资源，§6.3）
        backends_by_agent: Dict[str, List] = defaultdict(list)
        for a in agent_closure:
            for bk in export_backends:
                if bk.id in (a.backendIds or []) and bk.backendType == BackendType.RESOURCE.value:
                    backends_by_agent[a.id].append(bk)

        # 3. 收集挂载请求（顺序即优先级：主空间 > 子空间；prompt > memory > backend，§6.4）
        mounts: List[Tuple[_Space, str, str, Optional[str]]] = []
        for a in agent_closure:
            sp = spaces[a.id]
            for rid in (a.resourcePromptList or []):
                mounts.append((sp, "prompt", rid, None))
            ap = a.agentParameters or {}
            for rid in (ap.get("memory_resource_ids") or []):
                mounts.append((sp, "memory", rid, None))
            for bk in backends_by_agent.get(a.id, []):
                rid = (bk.configData or {}).get("resource_id")
                if rid:
                    mounts.append((sp, "backend", rid, bk.name))

        # 4. 加载显式挂载资源（含全部版本）
        explicit_ids = [m[2] for m in mounts]
        res_map = await self._load_resources_with_versions(explicit_ids)
        for m in mounts:
            if m[2] not in res_map:
                raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_RESOURCE_NOT_FOUND", detail=f"资源 {m[2]} 不存在，无法导出")

        # 5. 两阶段认领（§6.3/§6.4）：目录型挂载按 DB 树深度外层优先，整体认领完整子树；
        #    叶子挂载仅认领未被任何树包含的资源。同节点多挂载按认领顺序固定归属，
        #    其余挂载引用在导入时重写指向该份。
        mount_entries: List[Tuple[int, _Space, str, str, Optional[str]]] = []
        for idx, (sp, source, rid, bname) in enumerate(mounts):
            res = res_map[rid]
            kind, container_key = self._classify_mount(source, res, bname)
            mount_entries.append((idx, sp, kind, rid, container_key))

        # 5a. 目录型认领（外层优先：DB 树深度升序，同深度按收集顺序）
        dir_entries = [e for e in mount_entries
                       if e[2] in (_KIND_KB_ROOT, _KIND_SKILL_ROOT, _KIND_BACKEND_FOLDER)]
        depth_map = await self._compute_resource_depths([e[3] for e in dir_entries])
        dir_entries.sort(key=lambda e: (depth_map[e[3]], e[0]))

        placements: Dict[str, _Placement] = {}
        subtree_roots: List[Tuple[_Space, str, List]] = []
        extra_ids: set = set()
        claimed_ids: set = set()
        for idx, sp, kind, rid, container_key in dir_entries:
            if rid in claimed_ids:
                continue  # 已被更外层树认领为成员 / 同节点先到 → 引用重写
            placements[rid] = _Placement(res_map[rid], sp, kind, container_key)
            desc = await resource_crud.get_descendants_with_versions(self.db, rid)
            subtree_roots.append((sp, rid, desc))
            extra_ids.update(d.id for d in desc)
            claimed_ids.add(rid)
            claimed_ids.update(d.id for d in desc)

        extra_map = await self._load_resources_with_versions(list(extra_ids))
        for sp, rid, desc in subtree_roots:
            for d in desc:
                if d.id in placements:
                    continue  # 防御：深度排序下不应触发
                placements[d.id] = _Placement(extra_map[d.id], sp, _KIND_MEMBER, None)

        # 5b. 叶子认领（兜底，按收集顺序）
        for idx, sp, kind, rid, container_key in mount_entries:
            if kind != _KIND_LEAF or rid in placements:
                continue
            placements[rid] = _Placement(res_map[rid], sp, kind, container_key)

        all_res_map = {**res_map, **extra_map}

        # 7. 包内 parentId 解析
        for p in placements.values():
            if p.kind == _KIND_MEMBER:
                parent_res = all_res_map.get(p.resource.parentId)
                if parent_res is None or parent_res.id not in placements:
                    raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_RESOURCE_PARENT_NOT_IN_CLOSURE", detail=f"资源 '{p.resource.name}' 的父节点不在闭包内")
                p.package_parent = placements[parent_res.id].package_id
            # 根级 placement 的 package_parent 在虚拟容器生成后回填

        # 8. 空空间判定 + 虚拟容器生成（§6.4 末）
        vnodes: Dict[str, _VNode] = {}
        vnode_children: Dict[Optional[str], List[str]] = defaultdict(list)

        def space_has_resources(sp: _Space) -> bool:
            if any(p.space is sp and p.kind != _KIND_MEMBER for p in placements.values()):
                return True
            return any(space_has_resources(c) for c in sp.children)

        def build_space(sp: _Space, parent_vnode_id: Optional[str], root_of_tree: bool):
            # 空间根节点
            root = _VNode(sp.agent_name, parent_vnode_id)
            vnodes[root.package_id] = root
            vnode_children[parent_vnode_id].append(root.package_id)

            # 本空间显式挂载的容器键（保持出现顺序）
            key_order: List[str] = []
            for p in placements.values():
                if p.space is sp and p.kind != _KIND_MEMBER and p.container_key not in key_order:
                    key_order.append(p.container_key)

            fixed = [k for k in _FIXED_CONTAINERS if k in key_order]
            rb = [k for k in key_order if k.startswith("RB_")]
            others = [k for k in key_order if k not in fixed and not k.startswith("RB_")]
            ordered_keys = fixed + rb + others

            containers: Dict[str, _VNode] = {}
            idx = 0
            for key in ordered_keys:
                node = _VNode(key, root.package_id, idx)
                vnodes[node.package_id] = node
                vnode_children[root.package_id].append(node.package_id)
                containers[key] = node
                idx += 1

            # subagents 容器（任一子空间有资源）
            if any(space_has_resources(c) for c in sp.children):
                sub_node = _VNode("subagents", root.package_id, idx)
                vnodes[sub_node.package_id] = sub_node
                vnode_children[root.package_id].append(sub_node.package_id)
                containers["subagents"] = sub_node
                idx += 1
                for child in sp.children:
                    if space_has_resources(child):
                        build_space(child, sub_node.package_id, False)

            # 回填根级 placement 的包内父节点
            for p in placements.values():
                if p.space is sp and p.kind != _KIND_MEMBER:
                    p.package_parent = containers[p.container_key].package_id

        main_space = spaces[main_agent.id]
        if space_has_resources(main_space):
            build_space(main_space, None, True)

        # 9. kb_id / kb_config 最终化（§6.7，以包内结构为准）
        vc_ids = set(vnodes.keys())
        for p in placements.values():
            if p.resource.resourceType == ResourceType.KNOWLEDGE_BASE.value:
                p.kb_id = None
                p.kb_config = None
                continue
            kb_id = self._nearest_kb_in_package(p, placements, vnodes)
            p.kb_id = kb_id
            p.kb_config = p.resource.kb_config if kb_id else None

        # 10. 名称校验与同级重名校验（§6.5）
        self._validate_names(main_agent, agent_closure, placements, vnodes)

        # 11. sortOrder 重编号（同父内稳定排序，保证导入端顺序确定）
        node_sort = self._renumber_sort_orders(placements, vnodes, vnode_children)

        return _ResourceClosureResult(
            placements=placements,
            vnodes=vnodes,
            vnode_children=vnode_children,
            node_sort=node_sort,
            kb_roots=[p.resource for p in placements.values()
                      if p.resource.resourceType == ResourceType.KNOWLEDGE_BASE.value],
        )

    def _classify_mount(self, source: str, res, bname: Optional[str]) -> Tuple[str, Optional[str]]:
        rt = res.resourceType
        if source == "prompt":
            if rt == ResourceType.KNOWLEDGE_BASE.value:
                return _KIND_KB_ROOT, "kb"
            if rt == ResourceType.SKILL.value:
                return _KIND_SKILL_ROOT, "skill"
            if rt in _LEAF_TYPES:
                return _KIND_LEAF, "prompt"
            raise AppHTTPException(
                status_code=400,
                error_code="AGENT_PACKAGE_INVALID_PROMPT_MOUNT",
                detail=f"资源 '{res.name}'（类型 {rt}）不能作为 prompt 资源挂载",
            )
        if source == "memory":
            if rt in _LEAF_TYPES:
                return _KIND_LEAF, "memory"
            raise AppHTTPException(
                status_code=400,
                error_code="AGENT_PACKAGE_INVALID_MEMORY_MOUNT",
                detail=f"资源 '{res.name}'（类型 {rt}）不能作为 memory 资源挂载",
            )
        # backend
        if rt is None or rt in (ResourceType.KNOWLEDGE_BASE.value, ResourceType.SKILL.value):
            return _KIND_BACKEND_FOLDER, f"RB_{bname}"
        raise AppHTTPException(
            status_code=400,
            error_code="AGENT_PACKAGE_INVALID_BACKEND_MOUNT",
            detail=f"资源 '{res.name}'（类型 {rt}）不能作为 backend 挂载的 folder",
        )

    async def _compute_resource_depths(self, resource_ids: List[str]) -> Dict[str, int]:
        """计算资源在 DB 资源树中的深度（根节点深度 0），供目录型挂载按外层优先认领（§6.4）。"""
        if not resource_ids:
            return {}
        ancestors = await resource_crud.get_batch_resource_ancestors(self.db, resource_ids)
        parent_map = {r.id: r.parentId for r in ancestors}
        depths: Dict[str, int] = {}
        for rid in resource_ids:
            depth = 0
            cur = rid
            seen: set = set()
            while cur in parent_map and parent_map[cur] is not None:
                if cur in seen:
                    raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_RESOURCE_TREE_CYCLE", detail=f"资源树存在环（节点 {cur}），无法导出")
                seen.add(cur)
                cur = parent_map[cur]
                depth += 1
                if depth > 1000:
                    raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_RESOURCE_TREE_DEPTH", detail=f"资源树深度异常（节点 {rid}），无法导出")
            depths[rid] = depth
        return depths

    def _nearest_kb_in_package(self, p: _Placement, placements: Dict[str, _Placement],
                               vnodes: Dict[str, _VNode]) -> Optional[str]:
        cur = p.package_parent
        while cur:
            if cur in placements:
                node = placements[cur]
                if node.resource.resourceType == ResourceType.KNOWLEDGE_BASE.value:
                    return cur
                cur = node.package_parent
            elif cur in vnodes:
                cur = vnodes[cur].parent_id
            else:
                break
        return None

    def _validate_names(self, main_agent, agent_closure, placements, vnodes):
        # 用户可控名称（Agent 名 / 资源名 / 主 Agent 名）逐一过 path_safe（§6.5）。
        # 固定容器名与 RB_<backend名> 为规范常量/前缀隔离名（§6.4），
        # 仅做非法字符检查（保留字冲突已被 RB_ 前缀或容器层级隔离）。
        names: List[Tuple[str, str]] = []
        names.append((main_agent.name, "主 Agent 名"))
        for a in agent_closure:
            names.append((a.name, "Agent 名"))
        for p in placements.values():
            names.append((p.resource.name, "资源名"))

        if len(main_agent.name) > 91:
            raise AppHTTPException(
                status_code=400,
                error_code="AGENT_PACKAGE_MAIN_AGENT_NAME_TOO_LONG",
                detail=f"主 Agent 名 '{main_agent.name}' 超过 91 字符，导入端无法构造 subagent 文件夹名，拒绝导出",
            )

        for name, label in names:
            try:
                validate_path_safe_name(name, label=label)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        for vn in vnodes.values():
            _check_illegal_chars(vn.name, "容器名")

        # 同级重名检查（同一父节点下子节点名唯一）
        children_map: Dict[Optional[str], List[Tuple[str, str]]] = defaultdict(list)
        for vn in vnodes.values():
            children_map[vn.parent_id].append((vn.name, vn.package_id))
        for p in placements.values():
            children_map[p.package_parent].append((p.resource.name, p.package_id))
        for parent_id, items in children_map.items():
            by_name: Dict[str, str] = {}
            for name, node_id in items:
                if name in by_name and by_name[name] != node_id:
                    raise AppHTTPException(
                        status_code=400,
                        error_code="AGENT_PACKAGE_DUPLICATE_SIBLING_NAME",
                        detail=f"目标结构中存在同级重名资源 '{name}'，拒绝导出",
                    )
                by_name[name] = node_id

    def _renumber_sort_orders(self, placements, vnodes, vnode_children) -> Dict[str, int]:
        node_sort: Dict[str, int] = {}
        children_map: Dict[Optional[str], List[Tuple[int, str, str]]] = defaultdict(list)
        for vn in vnodes.values():
            children_map[vn.parent_id].append((vn.sort_order, vn.name, vn.package_id))
        for p in placements.values():
            children_map[p.package_parent].append(
                (p.resource.sortOrder or 0, p.resource.name, p.package_id)
            )
        for parent_id, items in children_map.items():
            items.sort(key=lambda x: (x[0], x[1]))
            for i, (_, _, node_id) in enumerate(items):
                node_sort[node_id] = i
        return node_sort

    async def _load_resources_with_versions(self, ids: List[str]) -> Dict[str, resource_model.Resource]:
        if not ids:
            return {}
        result = await self.db.execute(
            select(resource_model.Resource)
            .options(
                selectinload(resource_model.Resource.versions),
                joinedload(resource_model.Resource.latest_version),
            )
            .where(resource_model.Resource.id.in_(ids))
        )
        return {r.id: r for r in result.scalars().all()}

    # ── blob 闭包（§4.3 / §6.8）──
    async def _build_blob_closure(self, res_ctx, agent_closure):
        file_ids: set = set()
        for p in res_ctx.placements.values():
            if p.resource.resourceType not in _FILE_LIKE_TYPES:
                continue
            for v in p.resource.versions:
                if v.content:
                    file_ids.add(v.content)
        for a in agent_closure:
            if a.agentAvatarId:
                file_ids.add(a.agentAvatarId)

        files = await file_crud.get_files_by_ids(self.db, list(file_ids))
        file_map = {f.id: f for f in files}

        data: Dict[str, bytes] = {}
        for fid in file_ids:
            f = file_map.get(fid)
            if f is None:
                raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_FILE_RECORD_NOT_FOUND", detail=f"文件记录 {fid} 不存在，无法导出")
            try:
                data[fid] = await self.file_service.get_file_content(fid)
            except HTTPException as e:
                raise AppHTTPException(
                    status_code=400,
                    error_code="AGENT_PACKAGE_FILE_CONTENT_MISSING",
                    detail=f"文件 '{f.filename}' 内容缺失（{e.detail}），无法导出",
                )
        return _BlobClosureResult(data=data, file_map=file_map)

    # ── Provider 闭包（§6.6）──
    async def _build_providers(self, agent_closure, kb_roots) -> List[PackageProvider]:
        referenced_model_ids: set = set()
        for a in agent_closure:
            if a.aiModelId:
                referenced_model_ids.add(a.aiModelId)
            ap = a.agentParameters or {}
            sr = ap.get("security_review") or {}
            if sr.get("model_id"):
                referenced_model_ids.add(sr["model_id"])
        for kb_root in kb_roots:
            for v in (kb_root.versions or []):
                attrs = v.attributes or {}
                if attrs.get("embedding_model_id"):
                    referenced_model_ids.add(attrs["embedding_model_id"])

        if not referenced_model_ids:
            return []

        result = await self.db.execute(
            select(provider_model.AIModel).where(provider_model.AIModel.id.in_(referenced_model_ids))
        )
        model_map = {m.id: m for m in result.scalars().all()}

        # embedding_model_id 悬空 → 导出报错（§5.4）
        for kb_root in kb_roots:
            for v in (kb_root.versions or []):
                attrs = v.attributes or {}
                emb_id = attrs.get("embedding_model_id")
                if emb_id and emb_id not in model_map:
                    raise AppHTTPException(
                        status_code=400,
                        error_code="AGENT_PACKAGE_EMBEDDING_MODEL_DANGLING",
                        detail=f"知识库 '{kb_root.name}' 的 embedding 模型引用悬空（{emb_id}），拒绝导出",
                    )

        provider_ids = {model_map[mid].providerId for mid in referenced_model_ids if mid in model_map}
        if not provider_ids:
            return []
        result = await self.db.execute(
            select(provider_model.AIProvider)
            .options(selectinload(provider_model.AIProvider.models))
            .where(provider_model.AIProvider.id.in_(provider_ids))
        )
        providers = list(result.scalars().all())

        packages: List[PackageProvider] = []
        for p in providers:
            models = [
                PackageModel(
                    sourceId=m.id,
                    modelId=m.modelId,
                    name=m.name,
                    meta_config=json.loads(m.meta_config) if m.meta_config else None,
                    model_type=m.model_type,
                    starred=m.starred,
                )
                for m in p.models
                if m.id in referenced_model_ids  # 模型级闭包（§5.3）
            ]
            packages.append(PackageProvider(
                sourceId=p.id,
                name=p.name,
                apiHost=p.apiHost,
                use_proxy=p.use_proxy,
                worker_type=p.worker_type,
                apiKeyMissing=True,  # 恒标记（§4.2）
                models=models,
            ))
        return packages

    # ── MCP 闭包（§6.8 / §5.5）──
    async def _build_mcp(self, agent_closure) -> List[PackageMcpServer]:
        mcp_ids: set = set()
        for a in agent_closure:
            mcp_ids.update(a.enabledMcpIds or [])
        if not mcp_ids:
            return []
        servers = await mcp_crud.get_mcp_servers_by_ids(self.db, list(mcp_ids))
        return [
            PackageMcpServer(
                sourceId=s.id,
                name=s.name,
                description=s.description,
                transportType=s.transportType,
                command=s.command,
                args=s.args,
                cwd=s.cwd,
                url=s.url,
                timeout=s.timeout,
                sse_read_timeout=s.sse_read_timeout,
                isEnabled=s.isEnabled,
            )
            for s in servers
        ]

    # ── 资源序列化 ──
    def _serialize_resources(self, res_ctx, blob_ctx) -> List[PackageResource]:
        # 包内拓扑序（父先子后，同父按 sortOrder）
        children_map: Dict[Optional[str], List[str]] = defaultdict(list)
        for vn in res_ctx.vnodes.values():
            children_map[vn.parent_id].append(vn.package_id)
        for p in res_ctx.placements.values():
            children_map[p.package_parent].append(p.package_id)

        order = []
        queue = deque(sorted(children_map.get(None, []), key=lambda x: res_ctx.node_sort[x]))
        visited = set()
        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            order.append(nid)
            queue.extend(sorted(children_map.get(nid, []), key=lambda x: res_ctx.node_sort[x]))

        result: List[PackageResource] = []
        for nid in order:
            sort_order = res_ctx.node_sort.get(nid, 0)
            if nid in res_ctx.vnodes:
                vn = res_ctx.vnodes[nid]
                result.append(PackageResource(
                    sourceId=vn.package_id,
                    name=vn.name,
                    description=None,
                    itemType=ResourceItemType.FOLDER.value,
                    resourceType=None,
                    parentId=vn.parent_id,
                    sortOrder=sort_order,
                    kb_id=None,
                    kb_config=None,
                    latestVersionId=None,
                    versions=[],
                ))
            else:
                p = res_ctx.placements[nid]
                result.append(self._serialize_resource(p, sort_order, blob_ctx))
        return result

    def _serialize_resource(self, p: _Placement, sort_order: int, blob_ctx) -> PackageResource:
        res = p.resource
        rt = res.resourceType
        versions = self._serialize_versions(res, rt, blob_ctx) if rt is not None else []
        return PackageResource(
            sourceId=p.package_id,
            name=res.name,
            description=res.description,
            itemType=res.itemType,
            resourceType=rt,
            parentId=p.package_parent,
            sortOrder=sort_order,
            kb_id=p.kb_id,
            kb_config=p.kb_config,
            latestVersionId=res.latestVersionId,
            versions=versions,
        )

    def _serialize_versions(self, res, rt: Optional[str], blob_ctx) -> List[PackageResourceVersion]:
        sorted_versions = sorted(res.versions or [], key=lambda v: (v.sortOrder or 0, v.createdAt or v.id))
        out: List[PackageResourceVersion] = []
        if rt in _FILE_LIKE_TYPES:
            for i, v in enumerate(sorted_versions):
                fid = v.content
                if not fid:
                    raise AppHTTPException(
                        status_code=400,
                        error_code="AGENT_PACKAGE_VERSION_FILE_REF_MISSING",
                        detail=f"资源 '{res.name}' 的版本 '{v.name}' 缺少文件内容引用，无法导出",
                    )
                data = blob_ctx.data.get(fid)
                if data is None:
                    raise AppHTTPException(
                        status_code=400,
                        error_code="AGENT_PACKAGE_VERSION_CONTENT_MISSING",
                        detail=f"资源 '{res.name}' 的版本 '{v.name}' 文件内容缺失，无法导出",
                    )
                f = blob_ctx.file_map[fid]
                attrs = v.attributes
                if attrs and "last_ingest_config" in attrs:
                    attrs = {k: val for k, val in attrs.items() if k != "last_ingest_config"}
                out.append(PackageResourceVersion(
                    sourceId=v.id,
                    name=v.name,
                    sortOrder=i,
                    commitMessage=v.commitMessage,
                    contentType="file",
                    file=PackageFileRef(
                        filename=f.filename,
                        mimeType=f.mime_type,
                        size=len(data),
                        blobId=fid,
                    ),
                    attributes=attrs,
                ))
        else:
            # 文本型：system_prompt / submessage_template / KB 根初始配置
            for i, v in enumerate(sorted_versions):
                out.append(PackageResourceVersion(
                    sourceId=v.id,
                    name=v.name,
                    sortOrder=i,
                    commitMessage=v.commitMessage,
                    contentType="text",
                    content=v.content or "",
                    attributes=v.attributes,
                ))
        return out


class _ResourceClosureResult:
    def __init__(self, placements, vnodes, vnode_children, node_sort, kb_roots):
        self.placements = placements
        self.vnodes = vnodes
        self.vnode_children = vnode_children
        self.node_sort = node_sort
        self.kb_roots = kb_roots


class _BlobClosureResult:
    def __init__(self, data: Dict[str, bytes], file_map):
        self.data = data
        self.file_map = file_map


# ═══════════════════════════════════════════════════════════════
# 导入器
# ═══════════════════════════════════════════════════════════════

class AgentPackageImporter:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)
        self.kb_service = KnowledgeBaseService(db)

    # ── 解析与基础校验（§7.1 步 1-3 / §7.3）──
    def load_package(self, raw: bytes) -> AgentPackage:
        if len(raw) > MAX_PACKAGE_FILE_SIZE:
            raise AppHTTPException(
                status_code=413,
                error_code="AGENT_PACKAGE_TOO_LARGE",
                detail=f"包文件过大（{len(raw) // 1024 // 1024} MB），上限为 {MAX_PACKAGE_FILE_SIZE // 1024 // 1024} MB",
            )
        try:
            data = gzip.decompress(raw)
        except Exception:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_INVALID_GZIP", detail="不是有效的 gzip 文件，格式错误")
        if len(data) > MAX_TOTAL_DECODED_SIZE:
            raise AppHTTPException(status_code=413, error_code="AGENT_PACKAGE_TOO_LARGE", detail="解码后内容超过 500 MB 上限")
        try:
            obj = json.loads(data)
        except Exception:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_INVALID_JSON", detail="gzip 内容不是有效 JSON，格式错误")
        try:
            pkg = AgentPackage.model_validate(obj)
        except ValidationError as e:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_SCHEMA_INVALID", detail=f"包格式错误: {e.errors()[0].get('msg', '') if e.errors() else e}")

        if pkg.format != FORMAT:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_FORMAT_MISMATCH", detail=f"不是 MamboChat Agent 包（format={pkg.format}）")
        if _version_tuple(pkg.formatVersion) > _version_tuple(SUPPORTED_FORMAT_VERSION):
            raise AppHTTPException(
                status_code=400,
                error_code="AGENT_PACKAGE_FORMAT_VERSION_UNSUPPORTED",
                detail=f"包格式版本 {pkg.formatVersion} 高于当前支持的 {SUPPORTED_FORMAT_VERSION}，请升级平台后再导入",
            )
        return pkg

    def build_blob_index(self, pkg: AgentPackage) -> Dict[str, Tuple[bytes, str, str]]:
        """blobId -> (bytes, filename, mimeType)，校验 size 一致与大小上限（§4.3/§7.3）。"""
        index: Dict[str, Tuple[bytes, str, str]] = {}
        total = 0
        for b in pkg.blobs:
            try:
                raw = base64.b64decode(b.data, validate=True)
            except Exception:
                raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_INVALID_BASE64", detail=f"blob {b.blobId} 不是合法 base64")
            if len(raw) != b.size:
                raise AppHTTPException(
                    status_code=400,
                    error_code="AGENT_PACKAGE_BLOB_SIZE_MISMATCH",
                    detail=f"blob {b.blobId} 解码后字节数（{len(raw)}）与 size（{b.size}）不一致",
                )
            if len(raw) > MAX_SINGLE_BLOB_SIZE:
                raise AppHTTPException(status_code=413, error_code="AGENT_PACKAGE_TOO_LARGE", detail=f"单个 blob 超过 20 MB 上限: {b.blobId}")
            total += len(raw)
            if total > MAX_TOTAL_DECODED_SIZE:
                raise AppHTTPException(status_code=413, error_code="AGENT_PACKAGE_TOO_LARGE", detail="解码后总内容超过 500 MB 上限")
            index[b.blobId] = (raw, b.filename, b.mimeType)
        return index

    def check_references(self, pkg: AgentPackage) -> List[str]:
        """引用完整性检查（§7.1 步 4）。返回错误列表，空列表表示通过。"""
        errors: List[str] = []
        agent_ids = {a.sourceId for a in pkg.agents}
        resource_ids = {r.sourceId for r in pkg.resources}
        model_ids = {m.sourceId for p in pkg.providers for m in p.models}
        mcp_ids = {m.sourceId for m in pkg.mcpServers}
        backend_ids = {b.sourceId for b in pkg.backends}
        blob_ids = {b.blobId for b in pkg.blobs}
        kb_ids = {r.sourceId for r in pkg.resources
                  if r.resourceType == ResourceType.KNOWLEDGE_BASE.value}

        for a in pkg.agents:
            if a.aiModelId and a.aiModelId not in model_ids:
                errors.append(f"Agent '{a.name}': aiModelId 引用不存在")
            ap = a.agentParameters or {}
            sr = ap.get("security_review") or {}
            if sr.get("model_id") and sr["model_id"] not in model_ids:
                errors.append(f"Agent '{a.name}': security_review.model_id 引用不存在")
            for rid in (a.resourcePromptList or []):
                if rid not in resource_ids:
                    errors.append(f"Agent '{a.name}': resourcePromptList 引用 {rid} 不存在")
            for rid in (ap.get("memory_resource_ids") or []):
                if rid not in resource_ids:
                    errors.append(f"Agent '{a.name}': memory_resource_ids 引用 {rid} 不存在")
            for mid in (a.enabledMcpIds or []):
                if mid not in mcp_ids:
                    errors.append(f"Agent '{a.name}': enabledMcpIds 引用 {mid} 不存在")
            for sid in (a.subAgents or []):
                if sid not in agent_ids:
                    errors.append(f"Agent '{a.name}': subAgents 引用 {sid} 不存在")
            for bid in (a.backendIds or []):
                if bid not in backend_ids:
                    errors.append(f"Agent '{a.name}': backendIds 引用 {bid} 不存在")
            if a.defaultBackendId and a.defaultBackendId not in backend_ids:
                errors.append(f"Agent '{a.name}': defaultBackendId 引用不存在")
            if a.agentAvatarId and a.agentAvatarId not in blob_ids:
                errors.append(f"Agent '{a.name}': agentAvatarId 引用不存在")

        for r in pkg.resources:
            if r.parentId and r.parentId not in resource_ids:
                errors.append(f"资源 '{r.name}': parentId 引用不存在")
            version_ids = {v.sourceId for v in r.versions}
            if r.latestVersionId and r.latestVersionId not in version_ids:
                errors.append(f"资源 '{r.name}': latestVersionId 引用不存在")
            if r.kb_id and r.kb_id not in kb_ids:
                errors.append(f"资源 '{r.name}': kb_id 引用不存在（必须指向 KB 根）")
            for v in r.versions:
                if v.contentType == "file":
                    if not v.file:
                        errors.append(f"资源 '{r.name}' 版本 '{v.name}': 文件型版本缺少 file 引用")
                    elif v.file.blobId not in blob_ids:
                        errors.append(f"资源 '{r.name}' 版本 '{v.name}': blobId 引用不存在")

        for b in pkg.backends:
            if b.backendType != BackendType.RESOURCE.value:
                continue  # local 类型 configData 无跨段引用（§5.6）
            rid = (b.configData or {}).get("resource_id")
            if rid and rid not in resource_ids:
                errors.append(f"Backend '{b.name}': configData.resource_id 引用不存在")

        return errors

    def validate_all_names(self, pkg: AgentPackage):
        """所有名称字段导入前过 validate_path_safe_name（§7.3）。

        虚拟容器（固定容器名 / RB_<backend名>）为规范常量或前缀隔离名；
        provider / backend 名创建入口无 path_safe 校验（DB 允许保留字名，
        且 backend 名由 RB_ 前缀隔离），故与导出端对称仅查非法字符。
        """
        for a in pkg.agents:
            validate_path_safe_name(a.name, label="Agent 名称")
        for r in pkg.resources:
            if self._is_virtual(r):
                _check_illegal_chars(r.name, "容器名")
            else:
                validate_path_safe_name(r.name, label="资源名称")
        for p in pkg.providers:
            _check_illegal_chars(p.name, "服务商名称")
        for b in pkg.backends:
            _check_illegal_chars(b.name, "Backend 名称")

    # ── 冲突改名计划（§7.2）──
    async def compute_rename_plan(self, pkg: AgentPackage, target_folder_id: Optional[str],
                                  name_overrides: Optional[Dict[str, str]]) -> _RenamePlan:
        plan = _RenamePlan()

        # 确定主 Agent（闭包内不被任何 subAgents 引用的节点）
        referenced = {sid for a in pkg.agents for sid in (a.subAgents or [])}
        mains = [a for a in pkg.agents if a.sourceId not in referenced]
        if len(mains) != 1:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_MAIN_AGENT_AMBIGUOUS", detail="无法确定包内主 Agent")
        main = mains[0]
        plan.main_source_id = main.sourceId

        target_parent = target_folder_id or "root"
        target_agents = await agent_crud.get_agents_by_parent_ids(self.db, [target_parent])
        existing_agent_names = {a.name for a in target_agents}

        # 1) 主 Agent 名
        main_new = self._override_or(main.name, name_overrides, main.sourceId)
        main_new = self._unique_name(main_new, existing_agent_names, set())
        plan.main_agent_name = main_new
        plan.main_agent_renamed = main_new != main.name
        plan.agents = {main.sourceId: main_new}

        # 2) 命名空间容器名（资源树根）
        if self._namespace_required(pkg):
            root_resources = await resource_crud.get_resources_by_parent_ids(self.db, ["root"])
            existing_res_names = {r.name for r in root_resources}
            ns_new = self._override_or(main_new, name_overrides, f"__namespace__")
            ns_new = self._unique_name(ns_new, existing_res_names, set())
            plan.namespace_name = ns_new
        else:
            plan.namespace_name = None

        # 3) subAgent 文件夹名（目标文件夹内，与主 Agent 同级）
        if len(pkg.agents) > 1:
            base = f"{main_new}{SUBAGENT_FOLDER_SUFFIX}"
            folder_new = self._override_or(base, name_overrides, "__subagent_folder__")
            folder_new = self._unique_name(folder_new, existing_agent_names, {main_new})
            plan.subagent_folder_name = folder_new
        else:
            plan.subagent_folder_name = None

        # 4) AIProvider（全局）
        providers = await provider_crud.get_providers(self.db)
        existing_provider_names = {p.name for p in providers}
        used_provider = set()
        for p in pkg.providers:
            new_name = self._override_or(p.name, name_overrides, p.sourceId)
            new_name = self._unique_name(new_name, existing_provider_names, used_provider)
            plan.providers[p.sourceId] = new_name
            used_provider.add(new_name)

        # 5) Backend（全局唯一）
        backends = await backend_crud.get_all_backends(self.db)
        existing_backend_names = {b.name for b in backends}
        used_backend = set()
        for b in pkg.backends:
            new_name = self._override_or(b.name, name_overrides, b.sourceId)
            new_name = self._unique_name(new_name, existing_backend_names, used_backend)
            plan.backends[b.sourceId] = new_name
            used_backend.add(new_name)

        # 6) 名称校验与长度限制（provider/backend 名仅查非法字符，与导出端对称；
        #    agent/命名空间/文件夹名保持完整 path_safe —— 其创建入口已有该校验）
        all_names = [
            main_new, plan.namespace_name, plan.subagent_folder_name,
            *plan.providers.values(), *plan.backends.values(),
        ]
        for name in all_names:
            if not name:
                continue
            if len(name) > MAX_NAME_LEN:
                raise AppHTTPException(
                    status_code=400,
                    error_code="AGENT_PACKAGE_RENAME_TOO_LONG",
                    detail=f"改名结果 '{name}' 超过 {MAX_NAME_LEN} 字符上限，导入失败",
                )
            if name in (main_new, plan.namespace_name, plan.subagent_folder_name):
                try:
                    validate_path_safe_name(name, label="改名结果")
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
            else:
                _check_illegal_chars(name, "改名结果")

        # 7) 建议清单
        if plan.main_agent_renamed:
            plan.suggestions.append(RenameSuggestion(
                entity_type="agent", source_id=main.sourceId,
                original_name=main.name, new_name=main_new,
            ))
        for sid, new_name in plan.providers.items():
            orig = next(p.name for p in pkg.providers if p.sourceId == sid)
            if new_name != orig:
                plan.suggestions.append(RenameSuggestion(
                    entity_type="provider", source_id=sid, original_name=orig, new_name=new_name,
                ))
        for sid, new_name in plan.backends.items():
            orig = next(b.name for b in pkg.backends if b.sourceId == sid)
            if new_name != orig:
                plan.suggestions.append(RenameSuggestion(
                    entity_type="backend", source_id=sid, original_name=orig, new_name=new_name,
                ))
        return plan

    @staticmethod
    def _namespace_required(pkg: AgentPackage) -> bool:
        if pkg.backends:
            return True
        for a in pkg.agents:
            if a.resourcePromptList:
                return True
            ap = a.agentParameters or {}
            if ap.get("memory_resource_ids"):
                return True
        return False

    @staticmethod
    def _override_or(base: str, overrides: Optional[Dict[str, str]], key: str) -> str:
        if overrides and key in overrides and overrides[key]:
            return overrides[key]
        return base

    @staticmethod
    def _unique_name(base: str, existing: set, used: set) -> str:
        if base not in existing and base not in used:
            return base
        n = 1
        while True:
            cand = f"{base}_{n}"
            if cand not in existing and cand not in used:
                return cand
            n += 1

    # ── 目录树预览 ──
    def build_tree_preview(self, pkg: AgentPackage) -> List[ResourcePreviewNode]:
        by_id = {r.sourceId: r for r in pkg.resources}
        children_map: Dict[Optional[str], List] = defaultdict(list)
        for r in pkg.resources:
            children_map[r.parentId].append(r)
        for lst in children_map.values():
            lst.sort(key=lambda r: r.sortOrder)

        def build(r) -> ResourcePreviewNode:
            return ResourcePreviewNode(
                name=r.name,
                itemType=r.itemType,
                resourceType=r.resourceType,
                children=[build(c) for c in children_map.get(r.sourceId, [])],
            )

        return [build(r) for r in sorted(children_map.get(None, []), key=lambda r: r.sortOrder)]

    # ── 正式导入（§7.1 步 5-6 / §7.4）──
    async def do_import(self, pkg: AgentPackage, blob_index: Dict[str, Tuple[bytes, str, str]],
                        target_folder_id: Optional[str], plan: _RenamePlan) -> ImportReport:
        session_id = str(uuid.uuid4())
        session = ImportSession(session_id)
        report = ImportReport(
            import_session_id=session_id,
            success=True,
            providers_missing_api_key=[ProviderBrief(source_id=p.sourceId, name=p.name) for p in pkg.providers],
        )
        phase = "providers"
        failed_entity: Optional[str] = None

        try:
            # ── 1. providers ──
            model_id_map: Dict[str, str] = {}
            for p in pkg.providers:
                failed_entity = p.sourceId
                new_provider, model_map = await self._create_provider(p, plan.providers[p.sourceId])
                model_id_map.update(model_map)
                session.add("provider", p.sourceId, new_provider.id)

            # ── 2. resources（按包内 parentId 拓扑序）──
            phase = "resources"
            res_id_map: Dict[str, str] = {}
            for r in self._topo_resources(pkg):
                failed_entity = r.sourceId
                new_id = await self._create_resource_node(r, res_id_map, model_id_map, blob_index, session)
                res_id_map[r.sourceId] = new_id
                session.add("resource", r.sourceId, new_id)

            # ── 3. mcpServers ──
            phase = "mcp"
            mcp_id_map: Dict[str, str] = {}
            for m in pkg.mcpServers:
                failed_entity = m.sourceId
                new_mcp = await self._create_mcp_server(m)
                mcp_id_map[m.sourceId] = new_mcp.id
                session.add("mcp", m.sourceId, new_mcp.id)

            # ── 4. backends ──
            phase = "backends"
            backend_id_map: Dict[str, str] = {}
            for b in pkg.backends:
                failed_entity = b.sourceId
                new_backend = await self._create_backend(b, res_id_map, plan.backends[b.sourceId])
                backend_id_map[b.sourceId] = new_backend.id
                session.add("backend", b.sourceId, new_backend.id)

            # ── 5. agents ──
            phase = "agents"
            main_new_id = await self._create_agents(
                pkg, target_folder_id, plan, res_id_map, model_id_map,
                mcp_id_map, backend_id_map, blob_index, session,
            )
            report.main_agent_id = main_new_id

        except HTTPException as e:
            report.success = False
            report.failed_phase = phase
            report.failed_entity = failed_entity
            report.error = str(e.detail)
        except Exception as e:  # 系统级异常（§7.4）
            report.success = False
            report.failed_phase = phase
            report.failed_entity = failed_entity
            report.error = f"{type(e).__name__}: {e}"

        report.created = session.created
        _IMPORT_SESSIONS[session_id] = session
        return report

    @staticmethod
    def _topo_resources(pkg: AgentPackage) -> List:
        children_map: Dict[Optional[str], List] = defaultdict(list)
        for r in pkg.resources:
            children_map[r.parentId].append(r)
        for lst in children_map.values():
            lst.sort(key=lambda r: r.sortOrder)
        order: List = []
        queue = deque(children_map.get(None, []))
        visited: set = set()
        while queue:
            r = queue.popleft()
            if r.sourceId in visited:
                continue
            visited.add(r.sourceId)
            order.append(r)
            queue.extend(children_map.get(r.sourceId, []))
        return order

    def _is_virtual(self, r) -> bool:
        return r.itemType == ResourceItemType.FOLDER.value and r.resourceType is None and not r.versions

    async def _create_resource_node(self, r, res_id_map, model_id_map, blob_index, session) -> str:
        parent_id = res_id_map.get(r.parentId) if r.parentId else None
        if self._is_virtual(r):
            db_res = resource_model.Resource(
                id=generate_uuid(),
                name=r.name,
                description=r.description,
                itemType=ResourceItemType.FOLDER.value,
                resourceType=None,
                parentId=parent_id,
                sortOrder=r.sortOrder,
            )
            self.db.add(db_res)
            await self.db.commit()
            return db_res.id

        if r.resourceType == ResourceType.KNOWLEDGE_BASE.value:
            return await self._create_kb_root(r, parent_id, model_id_map)

        # 普通资源（含全部版本）
        res_id = generate_uuid()
        sorted_versions = sorted(r.versions, key=lambda v: v.sortOrder)
        db_res = resource_model.Resource(
            id=res_id,
            name=r.name,
            description=r.description,
            itemType=r.itemType,
            resourceType=r.resourceType,
            parentId=parent_id,
            sortOrder=r.sortOrder,
            kb_id=res_id_map.get(r.kb_id) if r.kb_id else None,
            kb_config=r.kb_config,
        )
        self.db.add(db_res)
        await self.db.flush()

        latest_new_id: Optional[str] = None
        for i, v in enumerate(sorted_versions):
            if v.contentType == "file":
                file_id = await self._ensure_file(v.file.blobId, blob_index, session,
                                                  [FileManagementType.RESOURCE.value], "resources")
                content = file_id
            else:
                content = v.content or ""
            vid = generate_uuid()
            self.db.add(resource_model.ResourceVersion(
                id=vid,
                resourceId=res_id,
                name=v.name,
                sortOrder=i,
                commitMessage=v.commitMessage,
                content=content,
                attributes=v.attributes,
            ))
            if v.sourceId == r.latestVersionId:
                latest_new_id = vid
        if latest_new_id:
            db_res.latestVersionId = latest_new_id
        await self.db.commit()
        return res_id

    async def _create_kb_root(self, r, parent_id: Optional[str], model_id_map: Dict[str, str]) -> str:
        """KB 根：create_knowledge_base 等价逻辑（§7.1 步 5.2）。"""
        attrs = dict(r.versions[0].attributes) if r.versions and r.versions[0].attributes else {}
        emb_source = attrs.get("embedding_model_id")
        if not emb_source or emb_source not in model_id_map:
            raise AppHTTPException(
                status_code=400,
                error_code="AGENT_PACKAGE_EMBEDDING_MODEL_MISSING",
                detail=f"知识库 '{r.name}' 缺少有效的 embedding_model_id 引用",
            )
        new_model_id = model_id_map[emb_source]
        rate_limit = attrs.get("embedding_rate_limit", 0.0)

        kb_res = await self.kb_service.create_knowledge_base(kb_schemas.KBCreate(
            name=r.name,
            description=r.description,
            parent_id=parent_id,
            embedding_model_id=new_model_id,
            embedding_rate_limit=rate_limit,
        ))

        # 重新加载（含 versions），删除自动生成的 v1，仅保留唯一"初始配置"版本并原地更新
        kb_full = await resource_crud.get_resource_with_versions(self.db, kb_res.id)
        latest_ver = kb_full.latest_version
        for v in list(kb_full.versions or []):
            if latest_ver and v.id != latest_ver.id:
                await self.db.delete(v)
                await self.db.flush()
        if latest_ver is None:
            raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_KB_INITIAL_VERSION_MISSING", detail=f"知识库 '{r.name}' 创建后缺少初始版本")

        new_attrs = dict(attrs)
        new_attrs["embedding_model_id"] = new_model_id
        # dimension 以创建时按重写后模型推导为准（attributes 中的 dimension 不参与校验）
        await resource_crud.update_resource_version(
            self.db,
            latest_ver.id,
            resource_schemas.ResourceVersionUpdate(attributes=new_attrs, content=""),
        )
        kb_full.sortOrder = r.sortOrder
        await self.db.commit()
        return kb_full.id

    async def _ensure_file(self, blob_id: str, blob_index, session: ImportSession,
                           management_type: List[str], sub_path: str) -> str:
        if blob_id in session.blob_file_map:
            return session.blob_file_map[blob_id]
        data, filename, mime_type = blob_index[blob_id]
        file_rec = await self.file_service.save_file_from_bytes(
            data=data,
            filename=filename,
            mime_type=mime_type,
            management_type=management_type,
            sub_path=sub_path,
        )
        session.blob_file_map[blob_id] = file_rec.id
        session.add("file", blob_id, file_rec.id)
        return file_rec.id

    async def _create_provider(self, p: PackageProvider, new_name: str):
        provider_id = generate_uuid()
        db_provider = provider_model.AIProvider(
            id=provider_id,
            name=new_name,
            apiHost=p.apiHost,
            apiKey=API_KEY_PLACEHOLDER,  # 占位符（§4.2）
            use_proxy=p.use_proxy,
            worker_type=p.worker_type,
        )
        self.db.add(db_provider)
        await self.db.flush()
        model_map: Dict[str, str] = {}
        for m in p.models:
            model_id = generate_uuid()
            self.db.add(provider_model.AIModel(
                id=model_id,
                modelId=m.modelId,
                name=m.name,
                providerId=provider_id,
                meta_config=json.dumps(m.meta_config) if m.meta_config is not None else None,
                model_type=m.model_type,
                starred=m.starred,
            ))
            model_map[m.sourceId] = model_id
        await self.db.commit()
        return db_provider, model_map

    async def _create_mcp_server(self, m: PackageMcpServer):
        create = mcp_schemas.McpServerCreate(
            name=m.name,
            description=m.description,
            transportType=m.transportType,
            command=m.command,
            args=m.args,
            cwd=m.cwd,
            url=m.url,
            timeout=m.timeout,
            sse_read_timeout=m.sse_read_timeout,
            isEnabled=m.isEnabled,
        )
        return await mcp_crud.create_mcp_server(self.db, create)

    async def _create_backend(self, b: PackageBackend, res_id_map: Dict[str, str], new_name: str):
        cd = dict(b.configData or {})
        if b.backendType == BackendType.RESOURCE.value:
            # resource 类型：configData.resource_id 为跨段引用（§5.6），映射替换
            rid = cd.get("resource_id")
            if rid not in res_id_map:
                raise AppHTTPException(status_code=400, error_code="AGENT_PACKAGE_BACKEND_RESOURCE_REF_INVALID", detail=f"Backend '{b.name}' 的 resource_id 引用无效")
            cd["resource_id"] = res_id_map[rid]
        # local 类型：configData 无跨段引用（root_dir / 黑白名单 / ignore_dirs），原样落库
        # ORM 直建：绕过 BackendConfigCreate 的 path_safe 保留字校验
        # （backend 名由 RB_ 前缀隔离保留字，DB 允许保留字名，见 _check_illegal_chars 注释）
        db_backend = backend_model.BackendConfig(
            id=generate_uuid(),
            name=new_name,
            description=b.description,
            backendType=b.backendType,
            configData=cd,
            tools_config=b.tools_config,
        )
        self.db.add(db_backend)
        await self.db.commit()
        await self.db.refresh(db_backend)
        return db_backend

    async def _create_agents(self, pkg: AgentPackage, target_folder_id: Optional[str], plan: _RenamePlan,
                             res_id_map, model_id_map, mcp_id_map, backend_id_map,
                             blob_index, session: ImportSession) -> Optional[str]:
        agent_map: Dict[str, str] = {}

        # 1. subAgent 文件夹（与主 Agent 同级，§5.2）
        folder_id: Optional[str] = None
        if plan.subagent_folder_name:
            folder = await agent_crud.create_agent(self.db, agent_schemas.AgentCreate(
                name=plan.subagent_folder_name,
                itemType=AgentItemType.FOLDER,
                parentId=target_folder_id,
                backendIds=[],
            ))
            folder_id = folder.id
            session.add("agent", "", folder_id)

        # 2. subAgents 先建（主 Agent 的 subAgents 引用需指向新 id）
        main = next(a for a in pkg.agents if a.sourceId == plan.main_source_id)
        for a in pkg.agents:
            if a.sourceId == main.sourceId:
                continue
            avatar_id = await self._ensure_avatar(a, blob_index, session)
            new_agent = await agent_crud.create_agent(self.db, self._agent_create(
                a, folder_id, res_id_map, model_id_map, mcp_id_map, backend_id_map, avatar_id,
            ))
            agent_map[a.sourceId] = new_agent.id
            session.add("agent", a.sourceId, new_agent.id)

        # 3. 主 Agent（应用改名计划，§5.2/§7.1 步 5.6）
        main_avatar_id = await self._ensure_avatar(main, blob_index, session)
        main_create = self._agent_create(
            main, target_folder_id, res_id_map, model_id_map,
            mcp_id_map, backend_id_map, main_avatar_id,
        )
        main_create.name = plan.main_agent_name
        # 重写 subAgents 引用
        main_create.subAgents = [agent_map[sid] for sid in (main.subAgents or []) if sid in agent_map]
        main_new = await agent_crud.create_agent(self.db, main_create)
        agent_map[main.sourceId] = main_new.id
        session.add("agent", main.sourceId, main_new.id)
        return main_new.id

    async def _ensure_avatar(self, a: PackageAgent, blob_index, session: ImportSession) -> Optional[str]:
        if not a.agentAvatarId:
            return None
        return await self._ensure_file(
            a.agentAvatarId, blob_index, session,
            [FileManagementType.AGENT_AVATAR.value], "avatars",
        )

    def _agent_create(self, a: PackageAgent, parent_id: Optional[str], res_id_map, model_id_map,
                      mcp_id_map, backend_id_map, avatar_id: Optional[str]) -> agent_schemas.AgentCreate:
        ap = a.agentParameters
        if ap:
            ap = self._rewrite_agent_parameters(ap, res_id_map, model_id_map)

        return agent_schemas.AgentCreate(
            name=a.name,
            description=a.description,
            itemType=AgentItemType.AGENT,
            parentId=parent_id,
            AgentType=a.AgentType,
            systemPrompt=a.systemPrompt,
            modelParameters=a.modelParameters,
            agentParameters=ap,
            aiModelId=model_id_map.get(a.aiModelId) if a.aiModelId else None,
            agentAvatarId=avatar_id,
            resourcePromptList=[res_id_map[x] for x in (a.resourcePromptList or []) if x in res_id_map],
            enabledMcpIds=[mcp_id_map[x] for x in (a.enabledMcpIds or []) if x in mcp_id_map],
            subAgents=[],
            backendIds=[backend_id_map[x] for x in (a.backendIds or []) if x in backend_id_map],
            defaultBackendId=backend_id_map.get(a.defaultBackendId) if a.defaultBackendId else None,
        )

    @staticmethod
    def _rewrite_agent_parameters(ap: Dict[str, Any], res_id_map, model_id_map) -> Dict[str, Any]:
        out = dict(ap)
        mem = out.get("memory_resource_ids")
        if mem:
            out["memory_resource_ids"] = [res_id_map[x] for x in mem if x in res_id_map]
        sr = out.get("security_review")
        if isinstance(sr, dict) and sr.get("model_id"):
            sr = dict(sr)
            sr["model_id"] = model_id_map.get(sr["model_id"])
            out["security_review"] = sr
        return out

    # ── 清理（§7.4 步 3）──
    async def cleanup_import_session(self, session_id: str) -> CleanupReport:
        session = _IMPORT_SESSIONS.pop(session_id, None)
        if session is None:
            raise AppHTTPException(status_code=404, error_code="AGENT_PACKAGE_IMPORT_SESSION_NOT_FOUND", detail="导入会话不存在")
        cleaned: List[str] = []
        for ent in reversed(session.created):
            try:
                if ent.entity_type == "agent":
                    await agent_crud.delete_agent(self.db, ent.new_id)
                elif ent.entity_type == "backend":
                    await backend_crud.delete_backend(self.db, ent.new_id)
                elif ent.entity_type == "mcp":
                    await mcp_crud.delete_mcp_server(self.db, ent.new_id)
                elif ent.entity_type == "resource":
                    await resource_crud.delete_resource(self.db, ent.new_id)
                elif ent.entity_type == "provider":
                    await provider_crud.delete_provider(self.db, ent.new_id)
                elif ent.entity_type == "file":
                    await self.file_service.delete_file(ent.new_id)
                cleaned.append(ent.new_id)
            except Exception:
                continue
        return CleanupReport(cleaned=cleaned)


# 供外部使用的会话查询（可选）
def get_import_session(session_id: str) -> Optional[ImportSession]:
    return _IMPORT_SESSIONS.get(session_id)
