# backend/services/generation/agent/mambo_resource_backend.py

"""Resource-tree backend for mambo_agents.

Maps the Resource DB tree (folders + typed resources) to the
``BackendProtocol`` virtual filesystem.  A single folder-type
Resource serves as the workspace root; its descendant sub-tree
is loaded into an in-memory cache for fast path resolution.

Content semantics by ResourceType:

* FOLDER (any)          → directory, no content
* RESOURCE (any)        → both a flat file + a ``$v`` version-folder
* FILE / KB_FILE        → version content is a file_id, resolved via FileService
* SYSTEM_PROMPT         → version content is the raw text (direct text type)
* SUBMESSAGE_TEMPLATE   → version content is the raw text (direct text type)

Version-folder convention
=========================
When version editing is enabled, every resource with ``itemType == RESOURCE``
appears as **both** a flat file and a version folder::

    /workspace/my_prompt      ← flat file (read/edit/write on active version)
    /workspace/my_prompt$v/   ← version folder (browse individual versions)

Inside the ``$v/`` folder, each ``ResourceVersion`` appears as a file named::

    {version_name}:{sort_order}:{active_flag}

where ``active_flag`` is ``"active"`` for the latest version, or empty.
Example: ``v1:0:active``, ``v2:1:``.

* ``ls`` does NOT show ``$v`` folders or their contents — they are invisible
  to normal directory listing to avoid confusing the agent.
* ``read`` / ``edit`` / ``write`` on the flat file → operates on active version
  (same as legacy behavior).
* ``read`` on a version file inside ``$v/`` → returns that version's content.
* ``edit`` / ``write(overwrite)`` on a version file → updates it **in-place**
  (no new version is created).  New versions cannot be added via ``write``.
* ``ls_version`` → the ONLY way to discover and list versions.
* ``grep`` / ``glob`` skip ``$v/`` files (they search the flat file path).

Safety invariants
=================
* Never write content into a FOLDER node
* Workspace boundary enforced on every path
* Path traversal (``..``) rejected
* Edit whitelist/blacklist (fnmatch on filename) gate all writes
  (version files inside ``$v/`` bypass the filter)
* New files are always created as ResourceType.FILE
* New versions cannot be created via ``write`` in ``$v/`` folders
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import fnmatch
import logging
import posixpath
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Callable, ClassVar

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from mambo_agents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    ReadSummarizer,
    Result,
    VirtualPath,
    WriteResult,
    _get_file_type,
    _get_mime_type,
)
from mambo_agents.backends.schemas import BackendError, ErrorCode
from mambo_agents.backends.utils import (
    detect_trailing_newline_mismatch,
    format_validation_error,
    format_with_line_numbers,
    TreeEntry,
    format_tree_entries,
)

from mambo_agents.backends.schemas import human_size

from backend.crud import resource_crud
from backend import schemas
from backend.models import resource_model
from backend.schemas.enums import ResourceItemType, ResourceType
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# cache dataclass
# ---------------------------------------------------------------------------


@dataclass
class _CachedNode:
    """Lightweight snapshot of one Resource row for in-memory path resolution."""

    id: str
    name: str
    parent_id: str | None
    is_dir: bool
    resource_type: str | None
    content: str | None
    desc: str
    size: int
    modified_at: str
    is_version_node: bool = False
    """True for $v folders and their version-file children — invisible to ls/grep/glob."""


# ---------------------------------------------------------------------------
# Content-type classification
# ---------------------------------------------------------------------------

_DIRECT_TEXT_TYPES: frozenset[str] = frozenset({
    ResourceType.SYSTEM_PROMPT.value,
    ResourceType.SUBMESSAGE_TEMPLATE.value,
})

_FILE_ID_TYPES: frozenset[str] = frozenset({
    ResourceType.FILE.value,
    ResourceType.KB_FILE.value,
})


def _is_direct_text_type(rt: str | None) -> bool:
    return rt in _DIRECT_TEXT_TYPES


def _is_file_id_type(rt: str | None) -> bool:
    return rt in _FILE_ID_TYPES


# Pre-compiled regex for UUID-like strings (36-char with dashes)
_UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def _looks_like_uuid(s: str) -> bool:
    """Return True if *s* looks like a UUID (e.g. file_id stored in content)."""
    return len(s) == 36 and bool(_UUID_RE.match(s))


# ---------------------------------------------------------------------------
# Version-folder constants & helpers
# ---------------------------------------------------------------------------

_VERSION_FOLDER_SUFFIX = "$v"
"""Suffix appended to resource names to mark them as version-folders."""

_SYNTHETIC_VERSION_PREFIX = "__v__"
"""Prefix for synthetic node IDs representing version files."""


def _is_synthetic_version_id(node_id: str) -> bool:
    """Return True if *node_id* is a synthetic version-file node."""
    return node_id.startswith(_SYNTHETIC_VERSION_PREFIX)


def _extract_version_id(node_id: str) -> str:
    """Extract the real DB version ID from a synthetic node ID."""
    if not node_id.startswith(_SYNTHETIC_VERSION_PREFIX):
        raise ValueError(f"Not a synthetic version ID: {node_id}")
    return node_id[len(_SYNTHETIC_VERSION_PREFIX):]


def _format_updated_at(dt: datetime | None) -> str:
    """Format a datetime to ISO-8601 string for cache storage."""
    if dt is None:
        return ""
    return dt.isoformat() if isinstance(dt, datetime) else str(dt)


# ---------------------------------------------------------------------------
# ls_version result model
# ---------------------------------------------------------------------------


class VersionInfo(BaseModel):
    """Single version entry returned by ``ls_version``."""

    model_config = ConfigDict(frozen=True)

    version_id: str = ""
    name: str = ""
    sort_order: int = 0
    is_active: bool = False
    updated_at: str = ""
    file_path: VirtualPath = Field(default_factory=lambda: VirtualPath("/"))
    """Virtual path to use with read/edit/write on this version file."""


class LsVersionResult(Result):
    """Result from ``ls_version()`` — ``ls``-style with direct paths."""

    versions: list[VersionInfo] | None = None

    def apply_reverse_translation(
        self,
        reverse_fn,
        target_ws_root: VirtualPath,
        virtual_prefix: VirtualPath,
    ) -> "LsVersionResult":
        if self.versions is None:
            return self
        versions = [
            v.model_copy(update={
                "file_path": reverse_fn(v.file_path, target_ws_root, virtual_prefix),
            })
            for v in self.versions
        ]
        return self.model_copy(update={"versions": versions})

    def __str__(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        if not self.versions:
            return "(no versions found)"
        lines: list[str] = []
        for v in self.versions:
            active_tag = " [ACTIVE]" if v.is_active else ""
            lines.append(
                f"{v.file_path}  -- {v.name}{active_tag} | order={v.sort_order} | {v.updated_at}"
            )
        return "\n".join(lines)


# ============================================================================
# MamboResourceBackend
# ============================================================================


class MamboResourceBackend(BackendProtocol):
    """Backend that exposes Resource sub-trees as a virtual filesystem.

    Supports two modes of loading:

    1. **Single-tree mode** (default):
       Provide a ``resource_id`` pointing to a folder-type Resource whose
       entire sub-tree is mapped under ``workspace_root``.

    2. **Shortcut composition mode** (via ``shortcuts``):
       Map resource IDs to virtual names under the workspace root.
       Each ``{name: resource_id}`` entry mounts the resource directly at
       ``{workspace_root}/{name}`` — like a symbolic link / rename.
       Folder resources are expanded recursively in-place; file resources
       appear as a single file at the shortcut name.

    Both modes can be used simultaneously.  Write/edit operations work
    transparently across both modes:

    * **Updating existing files** — works directly (uses the real DB id
      stored in the cached node).
    * **Creating new files under shortcut folders** — creates real DB
      folder entries under ``_root_resource_id`` to match the virtual path,
      then creates the new file within them.
    * **Shortcut-only mode** (``resource_id=None``) — write is *not*
      supported because there is no real root to parent new files under.
      Provide a ``resource_id`` alongside ``shortcuts`` to enable writes.

    Parameters
    ----------
    resource_id:
        The folder-type Resource whose sub-tree is the workspace root.
        Pass ``None`` when you only want shortcut mappings (read-only).
    session_factory:
        Async callable returning a fresh ``AsyncSession`` for each operation.
    shortcuts:
        Map virtual names to resource IDs, like symlinks or renames.
        Each resource is mounted directly at ``{workspace_root}/{name}``.
        Folder resources are expanded recursively in-place.  Example::

            shortcuts={
                "ref": "res_abc",          # file mounted as /workspace/ref
                "my-skill": "res_xyz",     # folder subtree at /workspace/my-skill/
            }
    workspace_root:
        Virtual root path (default ``"/workspace"``).
    edit_whitelist:
        ``fnmatch`` patterns for filenames allowed for write/edit.
        Mutually exclusive with *edit_blacklist*.
    edit_blacklist:
        ``fnmatch`` patterns for filenames forbidden for write/edit.
    max_read_chars:
        Character limit before summarization kicks in (inherited).
    summarizer:
        Callback for oversized text (inherited).
    """

    BACKEND_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset({"ls_version", "tree"})
    """Tool names exposed by this backend (used for UI tracking registration).

    The ``MamboAgentBuiltinToolProvider`` reads this class attribute to
    automatically register these tools for UI call tracking, avoiding
    the need to manually update ``BUILTIN_TOOLS``.
    """

    def __init__(
        self,
        resource_id: str | None,
        session_factory: Callable[[], AsyncSession],
        *,
        shortcuts: dict[str, str] | None = None,
        workspace_root: VirtualPath = VirtualPath("/workspace"),
        edit_whitelist: frozenset[str] | None = None,
        edit_blacklist: frozenset[str] | None = None,
        max_read_chars: int = 100_000,
        summarizer: ReadSummarizer | None = None,
        enable_version_editing: bool = True,
    ) -> None:
        super().__init__(max_read_chars=max_read_chars, summarizer=summarizer)

        if edit_whitelist is not None and edit_blacklist is not None:
            raise ValueError(
                "edit_whitelist and edit_blacklist are mutually exclusive."
            )

        if not isinstance(workspace_root, VirtualPath):
            workspace_root = VirtualPath(workspace_root)
        self.workspace_root = workspace_root
        self._root_resource_id = resource_id
        self._shortcuts: dict[str, str] = shortcuts or {}
        self._session_factory = session_factory
        self._edit_whitelist = edit_whitelist or frozenset()
        self._edit_blacklist = edit_blacklist or frozenset()
        self._enable_version_editing = enable_version_editing
        self._lock = asyncio.Lock()

        self._cache: dict[str, _CachedNode] = {}
        self._load_subtree()

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[StructuredTool]:
        wr = self.workspace_root.value
        tool_list: list[StructuredTool] = [
            StructuredTool(
                name="tree",
                description=(
                    "View the directory tree structure of the resource workspace. "
                    "Shows directories and files with their sizes in a tree format."
                ),
                args_schema=create_model(
                    "TreeSchema",
                    path=(VirtualPath, Field(default=VirtualPath(wr), description=f"Root directory to display (e.g. '{wr}')")),
                    depth=(int, Field(default=3, description="Maximum recursion depth")),
                ),
                func=self._safe_tool_func("tree", self.tree),
                coroutine=self._safe_tool_coroutine("tree", self.atree),
                handle_validation_error=format_validation_error,
            ),
        ]
        if self._enable_version_editing:
            tool_list.append(
                StructuredTool(
                    name="ls_version",
                    description=(
                        "List all versions of a resource. The path should point to "
                        "a resource (which appears as a `$v` folder in `ls` output). "
                        "The `$v` suffix is auto-appended if not present. "
                        "Returns version ID, name, order, active status, "
                        "content preview, and update time. "
                        "Use the version IDs from this listing to read/edit "
                        "specific version files inside the `$v/` folder."
                    ),
                    args_schema=create_model(
                        "LsVersionSchema",
                        path=(VirtualPath, Field(description=f"Path to a resource (e.g. '{wr}/my_prompt$v/' or '{wr}/my_prompt'). The '$v' suffix is auto-appended if missing.")),
                    ),
                    func=self._safe_tool_func("ls_version", self.ls_version),
                    coroutine=self._safe_tool_coroutine("ls_version", self.als_version),
                    handle_validation_error=format_validation_error,
                )
            )
        return tool_list

    @property
    def description(self) -> str:
        wr = self.workspace_root.value
        parts: list[str] = []
        if self._root_resource_id:
            parts.append(f"Rooted at resource '{self._root_resource_id}'")
        if self._shortcuts:
            sc_keys = ", ".join(f"'{k}'" for k in self._shortcuts)
            parts.append(f"Shortcuts: {sc_keys}")
        base = (
            f"Resource-tree backend. {'; '.join(parts)} "
            f"All file paths must be under '{wr}'. "
        )
        if self._enable_version_editing:
            base += (
                "Version editing is enabled. Resources work as normal flat files "
                "(read/edit/write on the active version). "
                "Use the ls_version tool (NOT ls) to discover and manage "
                "individual versions. ls will NOT show version folders. "
            )
        base += (
            "The read tool defaults to no line numbers. "
            "Set include_line_numbers=True when you need to reference "
            "specific lines."
        )
        return base

    # ==================================================================
    # Cache management
    # ==================================================================

    def _load_subtree(self) -> None:
        """Sync bootstrap: load the full sub-tree from DB into ``_cache``."""
        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                pool.submit(asyncio.run, self._arefresh_cache()).result()
            except Exception:
                logger.exception("Failed to load resource sub-tree cache")
                self._cache = {}

    async def _arefresh_cache(self) -> None:
        """Async: reload entire resource tree (main root + shortcuts) into ``_cache``."""
        cache: dict[str, _CachedNode] = {}

        async with self._session_factory() as db:
            # --- 1. Main root subtree ---
            if self._root_resource_id:
                root_res = await resource_crud.get_resource(
                    db, self._root_resource_id
                )
                if root_res is not None:
                    root_vpath = self.workspace_root.normalized
                    cache[root_vpath] = _resource_to_node(root_res)
                    await self._load_subtree_into_cache(
                        cache, db, self._root_resource_id, root_vpath
                    )

            # --- 2. Shortcut mappings ---
            await self._load_shortcuts_into_cache(cache, db)

            # --- 3. Resolve real file sizes for file-id backed nodes ---
            await self._resolve_file_sizes(cache, db)

        self._cache = cache

    async def _resolve_file_sizes(
        self,
        cache: dict[str, _CachedNode],
        db: AsyncSession,
    ) -> None:
        """Resolve real file sizes from FileService for FILE / KB_FILE type nodes.

        For direct-text types (SYSTEM_PROMPT / SUBMESSAGE_TEMPLATE) the
        ``size`` is already correctly set from ``len(content)`` in
        ``_resource_to_node``.  For file-id types (FILE / KB_FILE) the
        ``content`` field stores a file_id UUID, not the actual content
        bytes, so we need to query the File table to get the real size.

        Also handles fallback cases where ``resource_type`` may be None
        or an unknown value but the ``content`` is still a file_id.
        """
        # Collect file_ids from candidates that need size resolution.
        # Using dict[str, list[str]] because multiple cache nodes (flat file
        # + version files inside $v/) can share the same file_id.
        file_id_to_vpaths: dict[str, list[str]] = {}  # file_id -> [vpath, ...]
        unknown_nodes: list[tuple[str, _CachedNode]] = []

        for vpath, node in cache.items():
            if node.is_dir:
                continue

            # Already resolved: direct-text types have correct size
            if _is_direct_text_type(node.resource_type):
                continue

            # File-id types: content IS a file_id
            if _is_file_id_type(node.resource_type) and node.content:
                file_id_to_vpaths.setdefault(node.content, []).append(vpath)
                continue

            # Fallback: resource_type is None / unknown, but content
            # looks like a UUID (36-char with dashes → possible file_id)
            if node.size == 0 and node.content and _looks_like_uuid(node.content):
                unknown_nodes.append((vpath, node))

        if not file_id_to_vpaths and not unknown_nodes:
            logger.info("[resource-backend] _resolve_file_sizes: no file-backed nodes found in cache (%d total nodes)",
                        len(cache))
            return

        # Batch-query File table for all collected file_ids
        all_file_ids: list[str] = list(file_id_to_vpaths.keys())
        all_file_ids.extend(n.content for _, n in unknown_nodes)

        fs = FileService(db)
        files = await fs.batch_get_files(all_file_ids)
        id_to_size: dict[str, int] = {f.id: f.size for f in files}

        resolved = 0
        total_nodes = sum(len(vps) for vps in file_id_to_vpaths.values())
        for file_id, vpaths in file_id_to_vpaths.items():
            actual_size = id_to_size.get(file_id, 0)
            if actual_size > 0:
                for vpath in vpaths:
                    cache[vpath].size = actual_size
                resolved += len(vpaths)
            else:
                logger.warning("[resource-backend] size NOT resolved for %d node(s) (file_id=%s not in File table)",
                               len(vpaths), file_id[:36])

        for vpath, node in unknown_nodes:
            actual_size = id_to_size.get(node.content, 0)  # type: ignore[arg-type]
            if actual_size > 0:
                node.size = actual_size
                resolved += 1

        logger.info("[resource-backend] _resolve_file_sizes: resolved %d / %d file-backed nodes (%d unique file_ids, %d fallback)",
                    resolved, total_nodes, len(file_id_to_vpaths), len(unknown_nodes))

    async def _load_subtree_into_cache(
        self,
        cache: dict[str, _CachedNode],
        db: AsyncSession,
        root_id: str,
        base_vpath: str,
    ) -> None:
        """Load all descendants of *root_id* and populate *cache*
        with virtual paths rooted at *base_vpath*.

        When ``_enable_version_editing`` is True, resources become
        ``$v`` version-folders with individual version files inside.
        When False, resources appear as flat files (legacy mode).
        """
        load_versions = self._enable_version_editing
        descendants = await self._load_descendants(db, root_id, load_versions=load_versions)
        if not descendants:
            return

        parent_map: dict[str, str | None] = {
            d.id: d.parentId for d in descendants
        }
        parent_map[root_id] = None
        name_map: dict[str, str] = {d.id: d.name for d in descendants}

        for res in descendants:
            virt = self._build_virtual_path(
                res.id, res.name, parent_map, name_map,
                root_id=root_id, base_vpath=base_vpath,
            )
            if not virt:
                continue

            if self._enable_version_editing and res.itemType == ResourceItemType.RESOURCE.value:
                # --- Resource: flat file + $v folder (additional view) ---
                # Flat file: same as before — read/edit/write on active version
                cache[virt] = _resource_to_node(res)
                # $v folder: exposes all versions as individual files
                folder_vpath = virt + _VERSION_FOLDER_SUFFIX
                cache[folder_vpath] = _CachedNode(
                    id=res.id,
                    name=res.name + _VERSION_FOLDER_SUFFIX,
                    parent_id=res.parentId,
                    is_dir=True,
                    resource_type=res.resourceType,
                    content=None,
                    desc=getattr(res, "description", None) or "",
                    size=0,
                    modified_at=_format_updated_at(res.updatedAt),
                    is_version_node=True,
                )
                self._load_versions_into_cache(cache, res, folder_vpath)
            else:
                # --- FOLDER or legacy mode RESOURCE → flat node only ---
                cache[virt] = _resource_to_node(res)

    def _load_versions_into_cache(
        self,
        cache: dict[str, _CachedNode],
        resource: resource_model.Resource,
        folder_vpath: str,
    ) -> None:
        """Populate *cache* with a version-file node for each version
        of *resource*, nested under *folder_vpath*.

        Version files are named by their UUID (e.g. ``{version_id}``).
        Metadata (name/order/active) is stored in ``desc`` for display.
        """
        versions = getattr(resource, "versions", None) or []
        if not versions:
            return

        active_version_id = resource.latestVersionId

        for ver in versions:
            is_active = (ver.id == active_version_id)
            ver_vpath = f"{folder_vpath}/{ver.id}"

            content = ver.content
            size = len(content) if content and _is_direct_text_type(resource.resourceType) else 0

            cache[ver_vpath] = _CachedNode(
                id=_SYNTHETIC_VERSION_PREFIX + ver.id,
                name=ver.id,
                parent_id=resource.id,
                is_dir=False,
                resource_type=resource.resourceType,
                content=content,
                desc=f"{ver.name}" + (" [ACTIVE]" if is_active else ""),
                size=size,
                modified_at=_format_updated_at(ver.updatedAt),
                is_version_node=True,
            )

    async def _load_shortcuts_into_cache(
        self,
        cache: dict[str, _CachedNode],
        db: AsyncSession,
    ) -> None:
        """Mount shortcut resources directly at ``{workspace_root}/{name}``.

        Each shortcut maps a virtual name to a single resource ID.
        Folder resources are expanded in-place (no extra nesting).
        When ``_enable_version_editing`` is True, resource shortcuts
        become ``$v`` version-folders.
        """
        for name, res_id in self._shortcuts.items():
            root_norm = self.workspace_root.normalized
            vpath = f"{root_norm}/{name}"

            res = await resource_crud.get_resource(db, res_id)
            if res is None:
                logger.warning("Shortcut resource %s not found ('%s')", res_id, name)
                continue

            is_folder = (
                res.itemType == ResourceItemType.FOLDER.value
                if hasattr(res, "itemType")
                else False
            )
            if is_folder:
                # 文件夹资源直接展开到 shortcut 路径下，根节点也注册为目录项
                cache[vpath] = _resource_to_node(res)
                await self._load_subtree_into_cache(cache, db, res_id, vpath)
            elif self._enable_version_editing:
                # Both: flat file + $v folder (additional version view)
                cache[vpath] = _resource_to_node(res)
                res_with_versions = await resource_crud.get_resource_with_versions(db, res_id)
                if res_with_versions is None:
                    continue
                folder_vpath = vpath + _VERSION_FOLDER_SUFFIX
                cache[folder_vpath] = _CachedNode(
                    id=res_with_versions.id,
                    name=name + _VERSION_FOLDER_SUFFIX,
                    parent_id=res_with_versions.parentId,
                    is_dir=True,
                    resource_type=res_with_versions.resourceType,
                    content=None,
                    desc=getattr(res_with_versions, "description", None) or "",
                    size=0,
                    modified_at=_format_updated_at(res_with_versions.updatedAt),
                    is_version_node=True,
                )
                self._load_versions_into_cache(cache, res_with_versions, folder_vpath)
            else:
                # Legacy mode: mount as flat file
                cache[vpath] = _resource_to_node(res)

    async def _load_descendants(
        self, db: AsyncSession, root_id: str | None = None,
        *, load_versions: bool = False,
    ) -> list[resource_model.Resource]:
        """CTE-recursive: load all descendants under *root_id*.

        If *root_id* is omitted, defaults to ``self._root_resource_id``.
        When *load_versions* is True, also eager-load all ResourceVersion rows.
        """
        actual_root = root_id or self._root_resource_id
        if actual_root is None:
            return []

        cte = (
            select(resource_model.Resource)
            .where(resource_model.Resource.id == actual_root)
            .cte(name="subtree", recursive=True)
        )

        child_t = resource_model.Resource
        cte = cte.union_all(
            select(child_t).join(cte, child_t.parentId == cte.c.id)
        )

        options = [joinedload(resource_model.Resource.latest_version)]
        if load_versions:
            options.append(selectinload(resource_model.Resource.versions))

        stmt = (
            select(resource_model.Resource)
            .options(*options)
            .join(cte, resource_model.Resource.id == cte.c.id)
            .where(resource_model.Resource.id != actual_root)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    def _build_virtual_path(
        self,
        res_id: str,
        res_name: str,
        parent_map: dict[str, str | None],
        name_map: dict[str, str],
        *,
        root_id: str | None = None,
        base_vpath: str | None = None,
    ) -> str | None:
        """Walk up parent chain to build the virtual path for a descendant node.

        Parameters
        ----------
        root_id:
            The root of the subtree.  Defaults to ``self._root_resource_id``.
        base_vpath:
            Virtual path prefix (the root's virtual location).
            Defaults to ``self.workspace_root``.
        """
        r_id = root_id or self._root_resource_id
        base = base_vpath or self.workspace_root.normalized

        pid = parent_map.get(res_id)
        if pid == r_id:
            return f"{base}/{res_name}"

        parts: list[str] = [res_name]
        current = pid
        while current and current != r_id:
            name = name_map.get(current)
            if name is None:
                return None
            parts.append(name)
            current = parent_map.get(current)

        parts.reverse()
        return f"{base}/{posixpath.join(*parts)}"

    # ==================================================================
    # Path resolution & validation
    # ==================================================================

    def _normalize_path(self, path: VirtualPath) -> str:
        """Ensure path starts with workspace_root; reject traversals.

        Accepts VirtualPath (preferred) or str (backward-compat).
        Returns a plain string for use as cache key.
        """
        if not isinstance(path, VirtualPath):
            path = VirtualPath(path)
        raw = path.value
        norm = posixpath.normpath(raw)

        wr = self.workspace_root.value
        if norm != wr and not norm.startswith(wr + "/"):
            raise BackendError(
                code=ErrorCode.OUTSIDE_WORKSPACE,
                path=path,
                message=f"路径在 workspace 外。所有路径必须在 '{wr}' 下。",
            )

        if ".." in PurePosixPath(raw).parts:
            raise BackendError(
                code=ErrorCode.PATH_TRAVERSAL,
                path=path,
                message="路径不能包含 '..' 穿越。",
            )

        return norm

    def _resolve(self, path: VirtualPath) -> _CachedNode | None:
        """Resolve a virtual path to a cached node."""
        try:
            norm = self._normalize_path(path)
        except BackendError:
            return None
        return self._cache.get(norm)

    def _check_edit_allowed(self, path: VirtualPath) -> bool:
        """Gate writes by filename whitelist/blacklist (fnmatch)."""
        filename = PurePosixPath(str(path)).name
        if self._edit_whitelist:
            return any(
                fnmatch.fnmatch(filename, pat) for pat in self._edit_whitelist
            )
        if self._edit_blacklist:
            return not any(
                fnmatch.fnmatch(filename, pat) for pat in self._edit_blacklist
            )
        return True

    @staticmethod
    def _split_parent_and_name(path: str, wr: str) -> tuple[str, str]:
        """Return (parent_vpath, filename) for a virtual path."""
        pp = PurePosixPath(path)
        name = pp.name
        parent = str(pp.parent)
        if parent == "/" or parent == wr.rstrip("/"):
            parent = wr
        return parent, name

    # ==================================================================
    # Core: ls  (async-first: _als_impl)
    # ==================================================================

    def ls(self, path: VirtualPath) -> LsResult:
        return self._sync_bridge(_LsResult, self._als_impl, path)

    async def als(self, path: VirtualPath) -> LsResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._als_impl(path)

    async def _als_impl(self, path: VirtualPath) -> LsResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return LsResult(error=e)

        # --- Validate target exists and is a directory ---
        target = self._resolve(norm)
        if target is None:
            return LsResult(error=BackendError(
                code=ErrorCode.NOT_FOUND,
                path=path,
                message=f"Path '{path}' not found",
            ))
        if not target.is_dir:
            return LsResult(error=BackendError(
                code=ErrorCode.NOT_DIR,
                path=path,
                message=f"'{path}' is not a directory",
            ))

        entries: list[FileInfo] = []
        prefix = norm.rstrip("/") + "/"

        for vpath, node in self._cache.items():
            if vpath == norm:
                continue
            if not vpath.startswith(prefix):
                continue
            # Skip version nodes — invisible to normal ls
            if node.is_version_node:
                continue
            # Must be a direct child (no intermediate '/')
            rel = vpath[len(prefix):]
            if "/" in rel:
                continue

            entries.append(FileInfo(
                path=VirtualPath(vpath),
                is_dir=node.is_dir,
                size=node.size,
                modified_at=node.modified_at,
                desc=node.desc,
            ))

        entries.sort(key=lambda fi: (not fi.is_dir, fi.path))
        return LsResult(entries=entries) if entries else LsResult(entries=[])

    # ==================================================================
    # Core: tree  (cache-based — no SSH needed)
    # ==================================================================

    def tree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        """Render a directory tree of the resource workspace.

        Traverses the in-memory cache to build a tree view showing
        directories and files with their sizes.

        Args:
            path: Root directory to display (default workspace root).
            depth: Maximum recursion depth (default 3).

        Returns:
            Formatted tree string.
        """
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return str(e)

        # --- Validate target exists and is a directory ---
        target = self._resolve(norm)
        if target is None:
            return str(BackendError(
                code=ErrorCode.NOT_FOUND,
                path=path,
                message=f"Path '{path}' not found",
            ))
        if not target.is_dir:
            return str(BackendError(
                code=ErrorCode.NOT_DIR,
                path=path,
                message=f"'{path}' is not a directory",
            ))

        prefix = norm.rstrip("/") + "/"

        # Collect visible entries: relative_path -> node
        entries_map: dict[str, _CachedNode] = {}
        for vpath, node in self._cache.items():
            if node.is_version_node:
                continue
            if vpath != norm and not vpath.startswith(prefix):
                continue
            rel = vpath[len(prefix):]
            if rel:
                entries_map[rel] = node

        # Sort by relative path for correct parent→child ordering
        sorted_paths = sorted(entries_map.keys())

        root_name = PurePosixPath(norm).name or norm.rstrip("/")
        tree_entries: list[TreeEntry] = [TreeEntry(name=root_name + "/", depth=0)]

        # First pass: identify all directories and their children count
        seen_dirs: set[str] = set()
        dir_has_visible_children: dict[str, bool] = {}

        for rel in sorted_paths:
            d = rel.count("/") + 1
            if d > depth:
                continue
            node = entries_map[rel]

            # Register parent directories along the path
            parts = PurePosixPath(rel).parts
            for i in range(1, len(parts)):
                parent_rel = str(PurePosixPath(*parts[:i]))
                if parent_rel not in seen_dirs:
                    seen_dirs.add(parent_rel)
                    dir_has_visible_children[parent_rel] = True

            if node.is_dir:
                seen_dirs.add(rel)

        # Second pass: check which directories to show and whether they're empty
        dirs_to_show: dict[str, _CachedNode] = {}
        for rel in sorted_paths:
            d = rel.count("/") + 1
            if d > depth:
                # Track that parent dir has depth-exceeded children
                if d == depth + 1:
                    parent_rel = str(PurePosixPath(rel).parent)
                    if parent_rel != "." and parent_rel in dir_has_visible_children:
                        pass  # mark handled below
                continue
            node = entries_map[rel]
            if node.is_dir:
                # Only show if depth <= depth
                if d <= depth:
                    dirs_to_show[rel] = node
                    # Check if this dir has visible children at depth <= depth
                    has_kids = any(
                        other.startswith(rel + "/")
                        and other != rel
                        for other in sorted_paths
                    )
                    dir_has_visible_children[rel] = has_kids

        # Build entries sorted by path (directories before sibling files)
        sorted_entries: list[tuple[str, TreeEntry]] = []

        for rel in sorted(dirs_to_show.keys()):
            d = rel.count("/") + 1
            if d > depth:
                continue
            has_kids = dir_has_visible_children.get(rel, False)
            if d == depth and has_kids:
                marker = "depth_exceeded"
            elif not has_kids:
                marker = "empty"
            else:
                marker = ""

            sort_path = rel + "/"
            sorted_entries.append((sort_path, TreeEntry(
                name=PurePosixPath(rel).name + "/",
                depth=d,
                marker=marker,
            )))

        for rel in sorted_paths:
            d = rel.count("/") + 1
            if d > depth:
                continue
            node = entries_map[rel]
            if node.is_dir:
                continue  # already handled above
            size_str = human_size(node.size)
            sorted_entries.append((rel, TreeEntry(
                name=f"{PurePosixPath(rel).name} ({size_str})",
                depth=d,
            )))

        sorted_entries.sort(key=lambda x: x[0])
        tree_entries.extend(e[1] for e in sorted_entries)

        return format_tree_entries(tree_entries)

    async def atree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        """Async wrapper: delegates to sync ``tree()`` via thread pool."""
        import asyncio
        return await asyncio.to_thread(self.tree, path, depth)

    # ==================================================================
    # Core: read  (async-first: _aread_raw_impl)
    # ==================================================================

    def read_raw(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        return self._sync_bridge(
            _ReadResult,
            self._aread_raw_impl,
            file_path, offset, limit, include_line_numbers,
        )

    async def aread_raw(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._aread_raw_impl(
                file_path, offset, limit, include_line_numbers,
            )

    async def aread(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
        *,
        _apply_max_chars: bool = True,
    ) -> ReadResult:
        """Override parent: call aread_raw directly, serialized via lock."""
        async with self._lock:
            result = await self._aread_raw_impl(
                file_path, offset, limit, include_line_numbers,
            )
        if _apply_max_chars:
            result = self._apply_read_limit(result, file_path)
        return result

    async def _aread_raw_impl(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return ReadResult(error=e)

        node = self._resolve(norm)
        if node is None:
            return ReadResult(error=BackendError(
                code=ErrorCode.NOT_FOUND,
                path=file_path,
                message=f"File '{file_path}' not found",
            ))
        if node.is_dir:
            return ReadResult(error=BackendError(
                code=ErrorCode.IS_DIR,
                path=file_path,
                message=f"'{file_path}' is a directory",
            ))

        # ---- fetch text content (binary → base64 fallback) ----
        text: str
        encoding: str = "utf-8"
        try:
            if _is_file_id_type(node.resource_type):
                text = await self._read_file_id_content(node)
            else:
                text = node.content or ""
        except UnicodeDecodeError:
            # Binary file → base64-encode so download_files can recover the bytes
            text, encoding = await self._read_file_id_as_base64(node, norm)
        except Exception as e:
            return ReadResult(
                content="",
                total_lines=0,
                encoding="utf-8",
                file_type=_get_file_type(norm),
                mime_type=_get_mime_type(norm),
                error=BackendError(
                    code=ErrorCode.IO_ERROR,
                    path=VirtualPath(norm),
                    message=f"Error reading '{norm}': {e}",
                ),
            )

        # ---- apply offset / limit / line numbers (text only) ----
        if encoding == "base64":
            return ReadResult(content=text, total_lines=1, encoding="base64",
                              file_type=_get_file_type(norm), mime_type=_get_mime_type(norm))

        lines = text.splitlines(keepends=True)
        total = len(lines)

        if total > 0 and offset >= total:
            return ReadResult(
                error=BackendError(
                    code=ErrorCode.INVALID,
                    message=f"Line offset {offset} exceeds file length ({total} lines)",
                )
            )

        sliced = lines[offset:] if limit is None else lines[offset: offset + limit]
        raw_text = "".join(sliced)

        if include_line_numbers:
            content = format_with_line_numbers(raw_text, start_line=offset + 1)
        else:
            content = raw_text

        return ReadResult(content=content, total_lines=total, encoding="utf-8")

    async def _read_file_id_content(self, node: _CachedNode) -> str:
        """Resolve a file_id content to its UTF-8 text via FileService."""
        if not node.content:
            return ""
        async with self._session_factory() as db:
            fs = FileService(db)
            raw = await fs.get_file_content(node.content)
        return raw.decode("utf-8")

    async def _read_file_id_as_base64(
        self, node: _CachedNode, norm: str,
    ) -> tuple[str, str]:
        """Resolve a binary file_id to base64-encoded string via FileService.

        Used as fallback when UTF-8 decode fails (images, PDFs, etc.).
        Returns ``(base64_str, "base64")`` so that ``download_files`` can
        recover the original bytes via ``base64.standard_b64decode``.
        """
        import base64
        if not node.content:
            return "", "base64"
        async with self._session_factory() as db:
            fs = FileService(db)
            raw = await fs.get_file_content(node.content)
        return base64.standard_b64encode(raw).decode("ascii"), "base64"

    # ==================================================================
    # Core: write  (async-first: _awrite_impl)
    # ==================================================================

    def write(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        return self._sync_bridge(
            _WriteResult, self._awrite_impl, file_path, content, overwrite,
        )

    async def awrite(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._awrite_impl(file_path, content, overwrite)

    async def _awrite_impl(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        # 1. Validate
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return WriteResult(error=e)

        # 2. Check target
        existing = self._resolve(norm)
        is_update = existing is not None

        # Determine if we're in a version-node context
        is_target_version_node = existing is not None and existing.is_version_node
        parent_path, _ = self._split_parent_and_name(norm, self.workspace_root.value)
        parent_node = self._resolve(VirtualPath(parent_path))
        is_parent_version_folder = parent_node is not None and parent_node.is_version_node

        # Whitelist/blacklist: bypass for version-nodes (synthetic names)
        if not is_target_version_node and not is_parent_version_folder:
            if not self._check_edit_allowed(norm):
                return WriteResult(
                    error=BackendError(
                        code=ErrorCode.EDIT_NOT_ALLOWED,
                        path=file_path,
                        message=f"Path '{file_path}' is not allowed for write. "
                                 "Check edit_whitelist / edit_blacklist.",
                    )
                )

        # Block new file creation inside $v/ folders
        if is_parent_version_folder and not is_update:
            return WriteResult(
                error=BackendError(
                    code=ErrorCode.INVALID,
                    path=file_path,
                    message=f"Cannot create new version in '{file_path}'. "
                             "Version files can only be edited (use edit tool) "
                             "or overwritten (use write with overwrite=True on "
                             "an existing version file).",
                )
            )

        if is_update:
            # SAFETY: refuse to write content into a folder
            if existing.is_dir:
                return WriteResult(
                    error=BackendError(
                        code=ErrorCode.IS_DIR,
                        path=file_path,
                        message=f"Cannot write '{file_path}': it is a folder, not a file.",
                    )
                )
            if not overwrite:
                return WriteResult(
                    error=BackendError(
                        code=ErrorCode.ALREADY_EXISTS,
                        path=file_path,
                        message=f"Cannot write '{file_path}': file exists. "
                                 "Use overwrite=True to replace.",
                    )
                )

        # 3. Perform write
        parent_path, filename = self._split_parent_and_name(
            norm, self.workspace_root.value
        )

        try:
            async with self._session_factory() as db:
                if is_update:
                    if existing.is_version_node:
                        # Version file → update version content in-place
                        await self._update_version_content(db, existing, content)
                    else:
                        await self._update_existing(db, norm, existing, content)
                else:
                    await self._create_new_file(db, parent_path, filename, content)
        except Exception as e:
            logger.exception("Write failed for '%s'", file_path)
            return WriteResult(error=BackendError(
                code=ErrorCode.IO_ERROR,
                path=file_path,
                message=f"Write failed: {e}",
            ))

        # 4. Refresh cache
        await self._arefresh_cache()
        return WriteResult(path=file_path)

    async def _update_existing(
        self,
        db: AsyncSession,
        virt_path: str,
        node: _CachedNode,
        content: str,
    ) -> None:
        """Overwrite an existing file by creating a new version.

        For FILE/KB_FILE types: save content via FileService → store file_id.
        For direct-text types: store content inline.
        """
        res = await resource_crud.get_resource_with_versions(db, node.id)
        if res is None:
            raise ValueError(f"Resource {node.id} not found in DB")

        # SAFETY: double-check not a folder
        if res.itemType != ResourceItemType.RESOURCE.value:
            raise ValueError(f"Resource {node.id} is not a writable file")

        latest = res.latest_version

        # Idempotent: if content unchanged, do nothing
        if _is_direct_text_type(node.resource_type):
            existing_text = latest.content if latest else ""
            if content == existing_text:
                return

        # Build new content value
        new_content_val: str
        if _is_file_id_type(node.resource_type):
            fs = FileService(db)
            db_file = await fs.save_file_from_bytes(
                data=content.encode("utf-8"),
                filename=node.name,
                mime_type="text/plain",
                management_type=["resource"],
                sub_path="resources",
            )
            new_content_val = db_file.id
        else:
            new_content_val = content

        new_ver = await resource_crud.create_resource_version(
            db, node.id,
            schemas.ResourceVersionCreate(
                name=f"Update {node.name}",
                content=new_content_val,
                attributes=latest.attributes if latest else {},
            ),
        )
        if new_ver:
            await resource_crud.set_active_version(db, node.id, new_ver.id)

    async def _update_version_content(
        self,
        db: AsyncSession,
        node: _CachedNode,
        content: str,
    ) -> None:
        """Update a specific version's content **in-place** (no new version).

        Used when writing/editing a version file inside a ``$v/`` folder.
        For FILE/KB_FILE types: save content via FileService → store file_id.
        For direct-text types: store content inline.
        """
        version_id = _extract_version_id(node.id)

        # Idempotent: if content unchanged, do nothing
        if _is_direct_text_type(node.resource_type):
            if content == (node.content or ""):
                return

        new_content_val: str
        if _is_file_id_type(node.resource_type):
            fs = FileService(db)
            db_file = await fs.save_file_from_bytes(
                data=content.encode("utf-8"),
                filename=node.name,
                mime_type="text/plain",
                management_type=["resource"],
                sub_path="resources",
            )
            new_content_val = db_file.id
        else:
            new_content_val = content

        await resource_crud.update_resource_version(
            db, version_id,
            schemas.ResourceVersionUpdate(content=new_content_val),
        )

    async def _create_new_file(
        self,
        db: AsyncSession,
        parent_path: str,
        filename: str,
        content: str,
    ) -> None:
        """Create a new FILE resource, building missing parent folders.

        SKILL detection: if *filename* is ``"SKILL.md"`` and the immediate
        parent folder was newly created during this call, that folder's
        ``resourceType`` is set to ``"skill"``.
        """
        # 1. Build / locate parent chain, track newly-created folders
        parent_id, new_folders = await self._ensure_parent_chain(
            db, parent_path
        )

        # 2. SKILL.md auto-detection
        #    If the file is "SKILL.md" and its immediate parent folder was
        #    just created in this call, set that folder's resourceType to SKILL.
        if filename == "SKILL.md" and new_folders:
            skill_folder_id = new_folders[-1]
            skill_folder = await resource_crud.get_resource(db, skill_folder_id)
            if skill_folder and skill_folder.resourceType != ResourceType.SKILL.value:
                skill_folder.resourceType = ResourceType.SKILL.value
                await db.commit()
                await db.refresh(skill_folder)

        # 3. Save content via FileService
        fs = FileService(db)
        db_file = await fs.save_file_from_bytes(
            data=content.encode("utf-8"),
            filename=filename,
            mime_type="text/plain",
            management_type=["resource"],
            sub_path="resources",
        )

        # 4. Create the resource
        await resource_crud.create_resource(
            db,
            schemas.ResourceCreate(
                name=filename,
                itemType=ResourceItemType.RESOURCE,
                resourceType=ResourceType.FILE,
                parentId=parent_id,
                initial_content=db_file.id,
                initial_attributes={},
            ),
        )

    async def _ensure_parent_chain(
        self,
        db: AsyncSession,
        parent_path: str,
    ) -> tuple[str | None, list[str]]:
        """Ensure every segment of *parent_path* exists.

        Creates real DB folders along the chain.  Virtual shortcut folder
        entries in cache (id starting with ``__sc__``) are **skipped** —
        when a write targets a path under a shortcut virtual folder, real
        folders are created under ``_root_resource_id`` to hold the new file.

        Returns
        -------
        (leaf_parent_id, new_folder_ids)
            *leaf_parent_id* — the resource ID of the final (leaf) folder.
            *new_folder_ids* — IDs of folders created during this call (in order).
        """
        if self._root_resource_id is None:
            raise ValueError(
                "无法创建文件：当前 Backend 处于只读模式（resource_id 为空）。"
                "请先在 Agent 设置中挂载一个资源文件夹以启用写入支持。"
            )

        wr_value = self.workspace_root.value
        if parent_path == wr_value:
            return self._root_resource_id, []

        rel = parent_path[len(wr_value):].lstrip("/")
        segments = [s for s in rel.split("/") if s]
        if not segments:
            return self._root_resource_id, []

        current_id: str | None = self._root_resource_id
        new_ids: list[str] = []

        for i, seg in enumerate(segments):
            target_vpath = (
                f"{wr_value}/{'/'.join(segments[: i + 1])}"
            )
            cached = self._cache.get(target_vpath)

            # Use cached real folder; skip virtual shortcut folders
            if cached and cached.is_dir and not cached.id.startswith("__sc__"):
                current_id = cached.id
                continue

            # Query DB
            existing = await resource_crud.get_resource_by_name_and_parent(
                db, seg, current_id
            )
            if existing:
                current_id = existing.id
                continue

            # Create missing folder (plain, resourceType unset)
            new_folder = await resource_crud.create_resource(
                db,
                schemas.ResourceCreate(
                    name=seg,
                    itemType=ResourceItemType.FOLDER,
                    parentId=current_id,
                ),
            )
            current_id = new_folder.id
            new_ids.append(new_folder.id)

        return current_id, new_ids

    # ==================================================================
    # Core: edit  (async-first: _aedit_impl)
    # ==================================================================

    def edit(
        self,
        file_path: VirtualPath,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        return self._sync_bridge(
            _EditResult,
            self._aedit_impl, file_path, old_str, new_str, replace_all=replace_all,
        )

    async def aedit(
        self,
        file_path: VirtualPath,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._aedit_impl(
                file_path, old_str, new_str, replace_all=replace_all,
            )

    async def _aedit_impl(
        self,
        file_path: VirtualPath,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        # 1. Validate
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return EditResult(error=e)

        if not self._check_edit_allowed(norm):
            return EditResult(
                error=BackendError(
                    code=ErrorCode.EDIT_NOT_ALLOWED,
                    path=file_path,
                    message=f"Path '{file_path}' is not allowed for edit. "
                             "Check edit_whitelist / edit_blacklist.",
                )
            )

        # 2. Read current content
        read_res = await self._aread_raw_impl(file_path, limit=1_000_000)
        if read_res.error:
            return EditResult(error=read_res.error)
        current = read_res.content or ""

        # 3. Normalize line endings
        old_str = old_str.replace("\r\n", "\n").replace("\r", "\n")
        new_str = new_str.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Count occurrences
        occurrences = current.count(old_str)

        if occurrences == 0:
            trail_mismatch = detect_trailing_newline_mismatch(
                old_str, current,
            )
            if trail_mismatch is not None:
                return trail_mismatch
            return EditResult(
                error=BackendError(
                    code=ErrorCode.OLD_STR_NOT_FOUND,
                    path=file_path,
                    message=f"Cannot edit '{file_path}': old_str not found in file. "
                             "Read the file first to see its exact content.",
                )
            )

        if occurrences > 1 and not replace_all:
            return EditResult(
                error=BackendError(
                    code=ErrorCode.MULTI_OCCURRENCES,
                    path=file_path,
                    message=f"Cannot edit '{file_path}': old_str appears "
                             f"{occurrences} times. Use replace_all=True.",
                )
            )

        # 5. Perform replacement
        new_content = current.replace(
            old_str, new_str, -1 if replace_all else 1
        )

        # 6. Write back (triggers new version)
        write_res = await self._awrite_impl(file_path, new_content, overwrite=True)
        if write_res.error:
            return EditResult(error=write_res.error)

        return EditResult(path=file_path, occurrences=occurrences)

    # ==================================================================
    # Core: grep  (async-first: _agrep_impl)
    # ==================================================================

    def grep(
        self,
        pattern: str,
        path: VirtualPath = VirtualPath("/workspace"),
        glob: str | None = None,
        regex: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> GrepResult:
        """Grep files under *path*.  Direct-text nodes are matched synchronously
        without any DB I/O; only file-id nodes (FILE / KB_FILE) go through
        the async bridge — and even then, concurrently via ``asyncio.gather``
        rather than one-at-a-time."""
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return GrepResult(error=e)

        prefix = norm.rstrip("/") + "/"

        compiled: re.Pattern | None = None
        if regex:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return GrepResult(error=BackendError(
                    code=ErrorCode.INVALID, message=f"Invalid regex pattern: {e}",
                ))

        matches: list[GrepMatch] = []

        # --- Phase 1 (sync): grep direct-text nodes inline — zero DB, zero blocking ---
        file_id_pairs: list[tuple[str, str]] = []  # (vpath, node_id)
        for vpath, node in self._cache.items():
            if node.is_version_node:
                continue
            if vpath != norm and not vpath.startswith(prefix):
                continue
            if glob is not None and not fnmatch.fnmatch(node.name, glob):
                continue

            if _is_direct_text_type(node.resource_type):
                for li, line in enumerate((node.content or "").splitlines(), start=1):
                    if compiled is not None:
                        if compiled.search(line):
                            matches.append(
                                GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                            )
                    else:
                        if pattern in line:
                            matches.append(
                                GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                            )
            elif _is_file_id_type(node.resource_type):
                file_id_pairs.append((vpath, node.id))

        # --- Phase 2 (async): grep file-id nodes via concurrent DB reads ---
        if file_id_pairs:
            result = self._sync_bridge(
                _GrepResult,
                self._grep_file_id_nodes,
                file_id_pairs, compiled, pattern,
            )
            if result.error:
                return result
            if result.matches:
                matches.extend(result.matches)

        # Apply offset / limit slicing
        return self._apply_grep_limit(matches, offset, limit)

    async def _grep_file_id_nodes(
        self,
        pairs: list[tuple[str, str]],
        compiled: re.Pattern | None,
        pattern: str,
    ) -> GrepResult:
        """Async helper: concurrently read + grep file-id nodes.
        Called from ``_sync_bridge`` inside a worker-thread event loop."""
        reads = [
            self._aread_raw_impl(VirtualPath(vpath), limit=500_000)
            for vpath, _ in pairs
        ]
        results = await asyncio.gather(*reads, return_exceptions=True)

        matches: list[GrepMatch] = []
        for (vpath, _), result in zip(pairs, results):
            if isinstance(result, BaseException):
                continue
            if result.error or result.content is None:
                continue

            for li, line in enumerate(result.content.splitlines(), start=1):
                if compiled is not None:
                    if compiled.search(line):
                        matches.append(
                            GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                        )
                else:
                    if pattern in line:
                        matches.append(
                            GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                        )

        return GrepResult(matches=matches)

    async def agrep(
        self,
        pattern: str,
        path: VirtualPath = VirtualPath("/workspace"),
        glob: str | None = None,
        regex: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> GrepResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._agrep_impl(pattern, path, glob, regex, offset, limit)

    async def _agrep_impl(
        self,
        pattern: str,
        path: VirtualPath = VirtualPath("/workspace"),
        glob: str | None = None,
        regex: bool = False,
        offset: int = 0,
        limit: int | None = None,
    ) -> GrepResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return GrepResult(error=e)

        prefix = norm.rstrip("/") + "/"

        compiled: re.Pattern | None = None
        if regex:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return GrepResult(error=BackendError(
                    code=ErrorCode.INVALID, message=f"Invalid regex pattern: {e}",
                ))

        matches: list[GrepMatch] = []

        # --- Phase 1 (sync): grep direct-text nodes inline — zero DB calls ---
        file_id_pairs: list[tuple[str, str]] = []
        for vpath, node in self._cache.items():
            if node.is_version_node:
                continue
            if vpath != norm and not vpath.startswith(prefix):
                continue
            if glob is not None and not fnmatch.fnmatch(node.name, glob):
                continue

            if _is_direct_text_type(node.resource_type):
                for li, line in enumerate((node.content or "").splitlines(), start=1):
                    if compiled is not None:
                        if compiled.search(line):
                            matches.append(
                                GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                            )
                    else:
                        if pattern in line:
                            matches.append(
                                GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000])
                            )
            elif _is_file_id_type(node.resource_type):
                file_id_pairs.append((vpath, node.id))

        # --- Phase 2 (async): grep file-id nodes concurrently ---
        if file_id_pairs:
            result = await self._grep_file_id_nodes(file_id_pairs, compiled, pattern)
            if result.matches:
                matches.extend(result.matches)

        # Apply offset / limit slicing
        return self._apply_grep_limit(matches, offset, limit)

    # ==================================================================
    # Core: glob  (async-first: _aglob_impl)
    # ==================================================================

    def glob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        return self._sync_bridge(
            _GlobResult, self._aglob_impl, pattern, path,
        )

    async def aglob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._aglob_impl(pattern, path)

    async def _aglob_impl(
        self, pattern: str, path: VirtualPath = VirtualPath("/workspace"),
    ) -> GlobResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return GlobResult(error=e)

        prefix = norm.rstrip("/") + "/"

        # fnmatch.fnmatch is applied to node.name (filename only), so any
        # directory prefix in *pattern* (e.g. "**/", "*/", "dir/") will
        # never match a bare filename.  Strip everything before the last
        # "/" — the directory scope is already enforced by the prefix
        # check (vpath.startswith(prefix)) above.
        name_pattern = pattern.rsplit("/", 1)[-1] if "/" in pattern else pattern

        matched: list[FileInfo] = []
        for vpath, node in self._cache.items():
            if node.is_version_node:
                continue
            if vpath != norm and not vpath.startswith(prefix):
                continue
            if not fnmatch.fnmatch(node.name, name_pattern):
                continue
            matched.append(FileInfo(
                path=VirtualPath(vpath),
                is_dir=node.is_dir,
                size=node.size,
                modified_at=node.modified_at,
                desc=node.desc,
            ))

        matched.sort(key=lambda fi: fi.path)
        return GlobResult(matches=matched)

    # ==================================================================
    # Extra: ls_version  (async-first: _als_version_impl)
    # ==================================================================

    def ls_version(self, path: VirtualPath) -> LsVersionResult:
        """List all versions of a resource by path (synchronous bridge)."""
        return self._sync_bridge(_LsVersionResult, self._als_version_impl, path)

    async def als_version(self, path: VirtualPath) -> LsVersionResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._als_version_impl(path)

    async def _als_version_impl(self, path: VirtualPath) -> LsVersionResult:
        """Async impl: list all versions of a resource.

        Accepts paths with or without the ``$v`` suffix:
          - ``/workspace/my_prompt$v/`` → direct
          - ``/workspace/my_prompt``    → auto-appended to ``...$v/``
        """
        try:
            raw = str(path)
        except Exception:
            raw = str(path)

        # Auto-append $v suffix if not present
        normalized = raw.rstrip("/")
        if not normalized.endswith(_VERSION_FOLDER_SUFFIX):
            normalized = normalized + _VERSION_FOLDER_SUFFIX

        try:
            norm = self._normalize_path(VirtualPath(normalized))
        except BackendError as e:
            return LsVersionResult(error=e)

        # Resolve the $v folder node
        folder_node = self._resolve(norm)
        if folder_node is None:
            return LsVersionResult(error=BackendError(
                code=ErrorCode.NOT_FOUND,
                message=f"Resource version folder '{normalized}' not found. "
                        f"Use ls to find resources (they end with '$v/').",
            ))
        if not folder_node.is_dir:
            return LsVersionResult(error=BackendError(
                code=ErrorCode.NOT_DIR,
                message=f"'{normalized}' is not a version folder. "
                        f"Version folders end with '$v/'.",
            ))

        # Collect version children from cache
        prefix = norm.rstrip("/") + "/"
        # Query DB for full version metadata (sort_order is not in cache)
        res_id = folder_node.id
        async with self._session_factory() as db:
            res = await resource_crud.get_resource_with_versions(db, res_id)
        if res is None or not res.versions:
            return LsVersionResult(versions=[])

        active_version_id = res.latestVersionId
        version_infos: list[VersionInfo] = []

        for ver in res.versions:
            is_active = (ver.id == active_version_id)
            ver_vpath = f"{norm.rstrip('/')}/{ver.id}"

            # Only include versions that exist in cache (consistency check)
            if ver_vpath not in self._cache:
                continue

            version_infos.append(VersionInfo(
                version_id=ver.id,
                name=ver.name,
                sort_order=ver.sortOrder,
                is_active=is_active,
                updated_at=_format_updated_at(ver.updatedAt),
                file_path=ver_vpath,
            ))

        version_infos.sort(key=lambda v: v.sort_order)
        return LsVersionResult(versions=version_infos) if version_infos else LsVersionResult(versions=[])

    # ==================================================================
    # Sync bridge
    # ==================================================================

    @staticmethod
    def _sync_bridge(result_cls: type, fn, *args, **kwargs):
        """Run an async function synchronously via asyncio.run in a thread.

        Always creates a fresh event loop in the thread pool — works from
        both sync contexts (main thread without loop) and async→thread
        delegates (e.g. asyncio.to_thread used by SkillsMiddleware).
        """
        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(asyncio.run, fn(*args, **kwargs)).result()
            except Exception as e:
                return _construct_error(result_cls, str(e))


# ==================================================================
# Helpers
# ==================================================================


def _resource_to_node(res: resource_model.Resource) -> _CachedNode:
    """Convert a Resource ORM object (with latest_version loaded) to a cached node."""
    lv = res.latest_version
    content = lv.content if lv else None

    size = 0
    if content and _is_direct_text_type(res.resourceType):
        size = len(content)

    modified = ""
    updated = res.updatedAt
    if updated:
        modified = (
            updated.isoformat()
            if isinstance(updated, datetime)
            else str(updated)
        )

    return _CachedNode(
        id=res.id,
        name=res.name,
        parent_id=res.parentId,
        is_dir=res.itemType == ResourceItemType.FOLDER.value,
        resource_type=res.resourceType,
        content=content,
        desc=getattr(res, "description", None) or "",
        size=size,
        modified_at=modified,
    )


def _construct_error(result_cls: type, msg: str):
    """Build an error-bearing result for any protocol result type."""
    try:
        return result_cls(error=BackendError(code=ErrorCode.IO_ERROR, message=msg))
    except Exception:
        # Fallback for result types without 'error' field
        return result_cls()


# Type aliases to pass class objects around
_LsResult = LsResult
_LsVersionResult = LsVersionResult
_ReadResult = ReadResult
_WriteResult = WriteResult
_EditResult = EditResult
_GrepResult = GrepResult
_GlobResult = GlobResult
