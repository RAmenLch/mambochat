# backend/services/generation/agent/mambo_resource_backend.py

"""Resource-tree backend for mambo_agents.

Maps the Resource DB tree (folders + typed resources) to the
``BackendProtocol`` virtual filesystem.  Every operation queries the
database directly – there is no in-memory cache.

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

Inside the ``$v/`` folder, each ``ResourceVersion`` appears as a file named by
its version ID (UUID).

* ``ls`` does NOT show ``$v`` folders or their contents — they are invisible
  to normal directory listing to avoid confusing the agent.
* ``read`` / ``edit`` / ``write`` on the flat file → operates on active version
* ``read`` on a version file inside ``$v/`` → returns that version's content.
* ``edit`` / ``write(overwrite)`` on a version file → updates it **in-place**
* ``ls_version`` → the ONLY way to discover and list versions.
* ``grep`` / ``glob`` skip ``$v/`` files (they search the flat file path).

Safety invariants
=================
* Never write content into a FOLDER node
* Workspace boundary enforced on every path
* Path traversal (``..``) rejected
* Edit whitelist/blacklist gate all writes
  (version files inside ``$v/`` bypass the filter)
* New files are always created as ResourceType.FILE
* New versions cannot be created via ``write`` in ``$v/`` folders
"""

from __future__ import annotations

import asyncio
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
from sqlalchemy.ext.asyncio import AsyncSession

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
from mambo_agents.backends.schemas import BackendError, ErrorCode, human_size
from mambo_agents.backends.utils import (
    detect_trailing_newline_mismatch,
    format_validation_error,
    format_with_line_numbers,
    TreeEntry,
    format_tree_entries,
    fnmatch_path,
)

from backend.crud import resource_crud
from backend import schemas
from backend.models import resource_model
from backend.schemas.enums import ResourceItemType, ResourceType
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Version-folder constants & helpers
# ---------------------------------------------------------------------------

_VERSION_FOLDER_SUFFIX = "$v"
"""Suffix appended to resource names to mark them as version-folders."""

_SYNTHETIC_VERSION_PREFIX = "__v__"
"""Prefix for synthetic node IDs representing version files."""


def _is_synthetic_version_id(node_id: str) -> bool:
    return node_id.startswith(_SYNTHETIC_VERSION_PREFIX)


def _extract_version_id(node_id: str) -> str:
    if not node_id.startswith(_SYNTHETIC_VERSION_PREFIX):
        raise ValueError(f"Not a synthetic version ID: {node_id}")
    return node_id[len(_SYNTHETIC_VERSION_PREFIX):]


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


# ---------------------------------------------------------------------------
# _Resolved – path resolution result
# ---------------------------------------------------------------------------


@dataclass
class _Resolved:
    """Result of resolving a virtual path to a resource / version."""

    id: str
    name: str
    is_dir: bool
    resource_type: str | None
    content: str | None
    desc: str
    size: int
    modified_at: str
    is_version_node: bool = False
    is_version_dir: bool = False


def _orm_to_resolved(
    res: resource_model.Resource,
    *,
    version: resource_model.ResourceVersion | None = None,
    is_version_node: bool = False,
) -> _Resolved:
    """Convert a Resource ORM object to a _Resolved."""
    lv = version or res.latest_version
    content = lv.content if lv else None

    size = 0
    if content and _is_direct_text_type(res.resourceType):
        size = len(content)

    modified = ""
    updated = res.updatedAt
    if updated:
        modified = updated.isoformat() if isinstance(updated, datetime) else str(updated)

    return _Resolved(
        id=res.id,
        name=res.name,
        is_dir=res.itemType == ResourceItemType.FOLDER.value,
        resource_type=res.resourceType,
        content=content,
        desc=getattr(res, "description", None) or "",
        size=size,
        modified_at=modified,
        is_version_node=is_version_node,
    )


# ============================================================================
# MamboResourceBackend
# ============================================================================


class MamboResourceBackend(BackendProtocol):
    """Backend that exposes Resource sub-trees as a virtual filesystem."""

    BACKEND_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset({"ls_version", "tree"})

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
    # Path resolution
    # ==================================================================

    def _normalize_path(self, path: VirtualPath) -> str:
        if not isinstance(path, VirtualPath):
            path = VirtualPath(path)
        raw = path.value
        norm = posixpath.normpath(raw)

        wr = self.workspace_root.value
        if norm != wr and not norm.startswith(wr + "/"):
            raise BackendError(
                code=ErrorCode.OUTSIDE_WORKSPACE,
                path=path,
                message="路径超出工作区",
            )

        if ".." in PurePosixPath(raw).parts:
            raise BackendError(
                code=ErrorCode.PATH_TRAVERSAL,
                path=path,
                message="路径不能包含 '..' 穿越。",
            )

        return norm

    async def _resolve_resource(
        self, db: AsyncSession, norm: str,
    ) -> _Resolved | None:
        """Resolve a normalized virtual path to a _Resolved node via DB queries."""
        wr = self.workspace_root.value

        if norm == wr:
            return _Resolved(
                id="__ws_root__",
                name=self.workspace_root.name or wr.strip("/"),
                is_dir=True,
                resource_type=None,
                content=None,
                desc="",
                size=0,
                modified_at="",
            )

        rel = norm[len(wr):].lstrip("/")
        segments = [s for s in rel.split("/") if s]
        if not segments:
            return None

        # --- pre-process: locate $v suffix, strip it, remember version_id ---
        clean_segments: list[str] = []
        v_idx = -1
        version_id: str | None = None

        for i, seg in enumerate(segments):
            if self._enable_version_editing and seg.endswith(_VERSION_FOLDER_SUFFIX):
                clean_segments.append(seg[:-len(_VERSION_FOLDER_SUFFIX)])
                v_idx = i
                if i + 1 < len(segments):
                    version_id = segments[i + 1]
                break
            clean_segments.append(seg)

        if not clean_segments:
            return None

        # --- first segment: shortcut or root child ---
        first_seg = clean_segments[0]
        current_res: resource_model.Resource | None = None

        if first_seg in self._shortcuts:
            shortcut_id = self._shortcuts[first_seg]
            current_res = await resource_crud.get_resource(db, shortcut_id)
        elif self._root_resource_id:
            current_res = await resource_crud.get_resource_by_name_and_parent_with_version(
                db, first_seg, self._root_resource_id,
            )
        else:
            return None

        if current_res is None:
            return None

        # --- walk remaining clean segments ---
        for seg in clean_segments[1:]:
            child = await resource_crud.get_resource_by_name_and_parent_with_version(
                db, seg, current_res.id,
            )
            if child is None:
                return None
            current_res = child

        # --- handle $v if present ---
        if v_idx >= 0:
            if version_id is not None:
                res_with_v = await resource_crud.get_resource_with_versions(db, current_res.id)
                if res_with_v and res_with_v.versions:
                    for ver in res_with_v.versions:
                        if ver.id == version_id:
                            r = _orm_to_resolved(current_res, version=ver, is_version_node=True)
                            r.id = _SYNTHETIC_VERSION_PREFIX + ver.id
                            return r
                return None
            else:
                r = _orm_to_resolved(current_res)
                r.is_dir = True
                r.is_version_dir = True
                return r

        return _orm_to_resolved(current_res)

    def _check_edit_allowed(self, path: VirtualPath) -> bool:
        path_str = str(path)
        if self._edit_whitelist:
            return any(
                path_str == prefix.rstrip("/") or path_str.startswith(prefix.rstrip("/") + "/")
                for prefix in self._edit_whitelist
            )
        if self._edit_blacklist:
            return not any(
                path_str == prefix.rstrip("/") or path_str.startswith(prefix.rstrip("/") + "/")
                for prefix in self._edit_blacklist
            )
        return True

    @staticmethod
    def _split_parent_and_name(path: str, wr: str) -> tuple[str, str]:
        pp = PurePosixPath(path)
        name = pp.name
        parent = str(pp.parent)
        if parent == "/" or parent == wr.rstrip("/"):
            parent = wr
        return parent, name

    # ==================================================================
    # Subtree helpers
    # ==================================================================

    async def _load_subtree_with_paths(
        self, db: AsyncSession, root_id: str, base_vpath: str,
    ) -> list[tuple[str, resource_model.Resource]]:
        """Return ``(virtual_path, Resource)`` for all descendants under *root_id*."""
        descendants = await resource_crud.get_descendants_with_versions(db, root_id)
        if not descendants:
            return []

        all_ids = [d.id for d in descendants] + [root_id]
        ancestors = await resource_crud.get_batch_resource_ancestors(db, all_ids)

        parent_map: dict[str, str | None] = {a.id: a.parentId for a in ancestors}
        parent_map[root_id] = None
        name_map: dict[str, str] = {a.id: a.name for a in ancestors}

        result: list[tuple[str, resource_model.Resource]] = []
        for d in descendants:
            vpath = _build_virtual_path(
                d.id, d.name, parent_map, name_map,
                root_id=root_id, base_vpath=base_vpath,
            )
            if vpath:
                result.append((vpath, d))
        return result

    async def _resolve_file_sizes_batch(
        self, db: AsyncSession, pairs: list[tuple[str, resource_model.Resource]],
    ) -> dict[str, int]:
        """Batch-resolve file sizes for file-id backed resources. Returns {vpath: size}."""
        file_ids: list[str] = []
        vpath_map: dict[str, list[str]] = {}  # file_id → [vpath, ...]

        for vpath, res in pairs:
            rt = res.resourceType
            if _is_file_id_type(rt) and res.latest_version and res.latest_version.content:
                fid = res.latest_version.content
                file_ids.append(fid)
                vpath_map.setdefault(fid, []).append(vpath)

        if not file_ids:
            return {}

        fs = FileService(db)
        files = await fs.batch_get_files(file_ids)
        id_to_size = {f.id: f.size for f in files}

        result: dict[str, int] = {}
        for fid, vpaths in vpath_map.items():
            sz = id_to_size.get(fid, 0)
            for vp in vpaths:
                result[vp] = sz
        return result

    # ==================================================================
    # Core: ls
    # ==================================================================

    def ls(self, path: VirtualPath) -> LsResult:
        return self._run_async(self._als_impl(path), LsResult)

    async def als(self, path: VirtualPath) -> LsResult:
        async with self._lock:
            return await self._als_impl(path)

    async def _als_impl(self, path: VirtualPath) -> LsResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return LsResult(error=e)

        async with self._session_factory() as db:
            target = await self._resolve_resource(db, norm)
            if target is None:
                return LsResult(error=BackendError(
                    code=ErrorCode.NOT_FOUND, path=path, message="路径不存在",
                ))
            if not target.is_dir:
                return LsResult(error=BackendError(
                    code=ErrorCode.NOT_DIR, path=path, message="目标是文件，不是目录",
                ))

            if target.id == "__ws_root__":
                if self._root_resource_id:
                    parent_id = self._root_resource_id
                elif self._shortcuts:
                    entries: list[FileInfo] = []
                    for name, rid in self._shortcuts.items():
                        try:
                            child_res = await resource_crud.get_resource(db, rid)
                        except Exception:
                            continue
                        if child_res is None:
                            continue
                        is_dir = child_res.itemType == ResourceItemType.FOLDER.value
                        entries.append(FileInfo(
                            path=VirtualPath(f"{norm.rstrip('/')}/{name}"),
                            is_dir=is_dir,
                            size=0,
                            modified_at="",
                            desc=getattr(child_res, "description", None) or "",
                        ))
                    entries.sort(key=lambda fi: (not fi.is_dir, fi.path))
                    return LsResult(entries=entries) if entries else LsResult(entries=[])
                else:
                    parent_id = None
            else:
                parent_id = target.id

            if parent_id is None:
                return LsResult(entries=[])

            children = await resource_crud.get_resources_by_parent_ids_with_versions(db, [parent_id])
            if not children:
                return LsResult(entries=[])

            # batch file sizes
            file_size_pairs = [
                (f"{norm.rstrip('/')}/{c.name}", c) for c in children
                if c.itemType == ResourceItemType.RESOURCE.value
            ]
            size_map = await self._resolve_file_sizes_batch(db, file_size_pairs)

            entries: list[FileInfo] = []
            for child in children:
                is_dir = child.itemType == ResourceItemType.FOLDER.value
                child_vpath_str = f"{norm.rstrip('/')}/{child.name}"

                size = 0
                modified = ""
                if not is_dir:
                    lv = child.latest_version
                    if lv:
                        if _is_direct_text_type(child.resourceType):
                            size = len(lv.content or "")
                        else:
                            size = size_map.get(child_vpath_str, 0)
                        if lv.updatedAt:
                            modified = lv.updatedAt.isoformat() if isinstance(lv.updatedAt, datetime) else str(lv.updatedAt)

                entries.append(FileInfo(
                    path=VirtualPath(child_vpath_str),
                    is_dir=is_dir,
                    size=size,
                    modified_at=modified,
                    desc=getattr(child, "description", None) or "",
                ))

            entries.sort(key=lambda fi: (not fi.is_dir, fi.path))
            return LsResult(entries=entries) if entries else LsResult(entries=[])

    # ==================================================================
    # Core: tree
    # ==================================================================

    def tree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        try:
            return asyncio.run(self._atree_impl(path, depth))
        except Exception as e:
            logger.exception("tree failed")
            return str(e)

    async def atree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        async with self._lock:
            return await self._atree_impl(path, depth)

    async def _atree_impl(self, path: VirtualPath, depth: int) -> str:
        if depth < 1:
            return f"Invalid depth value: {depth}. Depth must be a positive integer (>= 1)."
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return str(e)

        async with self._session_factory() as db:
            target = await self._resolve_resource(db, norm)
            if target is None:
                return str(BackendError(code=ErrorCode.NOT_FOUND, path=path, message="路径不存在"))
            if not target.is_dir:
                return str(BackendError(code=ErrorCode.NOT_DIR, path=path, message="目标是文件，不是目录"))

            if target.id == "__ws_root__":
                if not self._root_resource_id:
                    if not self._shortcuts:
                        return format_tree_entries([TreeEntry(name=norm.rstrip("/") + "/", depth=0)])
                    all_pairs: list[tuple[str, resource_model.Resource]] = []
                    for name, rid in self._shortcuts.items():
                        try:
                            child_res = await resource_crud.get_resource(db, rid)
                        except Exception:
                            continue
                        if child_res is None:
                            continue
                        shortcut_vpath = f"{norm.rstrip('/')}/{name}"
                        if child_res.itemType == ResourceItemType.FOLDER.value:
                            sub_pairs = await self._load_subtree_with_paths(db, rid, shortcut_vpath)
                            all_pairs.extend(sub_pairs)
                        else:
                            all_pairs.append((shortcut_vpath, child_res))
                    pairs = all_pairs
                    size_map = await self._resolve_file_sizes_batch(db, pairs)
                else:
                    root_id = self._root_resource_id
            else:
                root_id = target.id

            if target.id == "__ws_root__" and not self._root_resource_id and self._shortcuts:
                pass  # pairs already built above
            else:
                pairs = await self._load_subtree_with_paths(db, root_id, norm)
                size_map = await self._resolve_file_sizes_batch(db, pairs)

            # Build entries by relative path
            prefix = norm.rstrip("/") + "/"
            entries_map: dict[str, _Resolved] = {}
            for vpath, res in pairs:
                if vpath == norm:
                    continue
                rel = vpath[len(prefix):]
                if not rel:
                    continue
                lv = res.latest_version
                is_dir = res.itemType == ResourceItemType.FOLDER.value
                sz = 0
                if not is_dir:
                    if _is_direct_text_type(res.resourceType):
                        sz = len(lv.content) if lv and lv.content else 0
                    else:
                        sz = size_map.get(vpath, 0)
                entries_map[rel] = _Resolved(
                    id=res.id, name=res.name, is_dir=is_dir,
                    resource_type=res.resourceType,
                    content=None, desc="", size=sz, modified_at="",
                )

            return _build_tree_string(norm, entries_map, depth)

    # ==================================================================
    # Core: read
    # ==================================================================

    def read_raw(
        self, file_path: VirtualPath, offset: int = 0, limit: int | None = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        return self._run_async(
            self._aread_raw_impl(file_path, offset, limit, include_line_numbers),
            ReadResult,
        )

    async def aread_raw(
        self, file_path: VirtualPath, offset: int = 0, limit: int | None = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        async with self._lock:
            return await self._aread_raw_impl(file_path, offset, limit, include_line_numbers)

    async def aread(
        self, file_path: VirtualPath, offset: int = 0, limit: int | None = 2000,
        include_line_numbers: bool = False, *, _apply_max_chars: bool = True,
    ) -> ReadResult:
        async with self._lock:
            result = await self._aread_raw_impl(file_path, offset, limit, include_line_numbers)
        if _apply_max_chars:
            result = self._apply_read_limit(result, file_path)
        return result

    async def _aread_raw_impl(
        self, file_path: VirtualPath, offset: int = 0, limit: int | None = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        if offset < 0:
            return ReadResult(error=BackendError(
                code=ErrorCode.INVALID, path=file_path,
                message=f"offset must be non-negative, got {offset}",
            ))
        if limit is not None and limit < 1:
            return ReadResult(error=BackendError(
                code=ErrorCode.INVALID, path=file_path,
                message=f"limit must be >= 1 (or None for unlimited), got {limit}",
            ))
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return ReadResult(error=e)

        async with self._session_factory() as db:
            resolved = await self._resolve_resource(db, norm)
            if resolved is None:
                return ReadResult(error=BackendError(
                    code=ErrorCode.NOT_FOUND, path=file_path, message="文件不存在",
                ))
            if resolved.is_dir and not resolved.is_version_dir:
                return ReadResult(error=BackendError(
                    code=ErrorCode.IS_DIR, path=file_path, message="目标是目录",
                ))

            text: str
            encoding: str = "utf-8"
            file_type = _get_file_type(norm)

            try:
                if _is_file_id_type(resolved.resource_type):
                    text = await self._read_file_id_content(resolved.content)
                else:
                    text = resolved.content or ""
            except UnicodeDecodeError:
                if file_type != "text":
                    text, encoding = await self._read_file_id_as_base64(resolved.content, norm)
                else:
                    return ReadResult(error=BackendError(
                        code=ErrorCode.INVALID, path=VirtualPath(norm),
                        message="无法读取，不是可识别的文本或多媒体格式",
                    ))
            except Exception as e:
                return ReadResult(
                    content="", total_lines=0, encoding="utf-8",
                    file_type=file_type, mime_type=_get_mime_type(norm),
                    error=BackendError(
                        code=ErrorCode.IO_ERROR, path=VirtualPath(norm),
                        message=f"Error reading file: {e}",
                    ),
                )

        if encoding == "base64":
            return ReadResult(content=text, total_lines=1, encoding="base64",
                              file_type=file_type, mime_type=_get_mime_type(norm))

        lines = text.splitlines(keepends=True)
        total = len(lines)

        if total > 0 and offset >= total:
            return ReadResult(error=BackendError(
                code=ErrorCode.INVALID,
                message=f"Line offset {offset} exceeds file length ({total} lines)",
            ))

        sliced = lines[offset:] if limit is None else lines[offset: offset + limit]
        raw_text = "".join(sliced)

        if include_line_numbers:
            content = format_with_line_numbers(raw_text, start_line=offset + 1)
        else:
            content = raw_text

        return ReadResult(content=content, total_lines=total, encoding="utf-8")

    async def _read_file_id_content(self, file_id: str | None) -> str:
        if not file_id:
            return ""
        async with self._session_factory() as db:
            fs = FileService(db)
            raw = await fs.get_file_content(file_id)
        return raw.decode("utf-8")

    async def _read_file_id_as_base64(self, file_id: str | None, norm: str) -> tuple[str, str]:
        import base64
        if not file_id:
            return "", "base64"
        async with self._session_factory() as db:
            fs = FileService(db)
            raw = await fs.get_file_content(file_id)
        return base64.standard_b64encode(raw).decode("ascii"), "base64"

    # ==================================================================
    # Core: write
    # ==================================================================

    def write(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        return self._run_async(self._awrite_impl(file_path, content, overwrite), WriteResult)

    async def awrite(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        async with self._lock:
            return await self._awrite_impl(file_path, content, overwrite)

    async def _awrite_impl(
        self, file_path: VirtualPath, content: str, overwrite: bool = False,
    ) -> WriteResult:
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return WriteResult(error=e)

        async with self._session_factory() as db:
            existing = await self._resolve_resource(db, norm)
            is_update = existing is not None

            is_target_version_node = existing is not None and existing.is_version_node
            parent_path, _ = self._split_parent_and_name(norm, self.workspace_root.value)
            parent_node = await self._resolve_resource(db, parent_path)
            is_parent_version_folder = parent_node is not None and parent_node.is_version_dir

            if not is_target_version_node and not is_parent_version_folder:
                if not self._check_edit_allowed(norm):
                    return WriteResult(error=BackendError(
                        code=ErrorCode.EDIT_NOT_ALLOWED, path=file_path, message="路径不允许写入",
                    ))

            if is_parent_version_folder and not is_update:
                return WriteResult(error=BackendError(
                    code=ErrorCode.INVALID, path=file_path,
                    message="无法创建新版本文件。版本文件只能编辑（使用 edit 工具）或覆盖已有版本（对已有版本文件使用 write 并设置 overwrite=True）。",
                ))

            if is_update:
                if existing.is_dir:
                    return WriteResult(error=BackendError(
                        code=ErrorCode.IS_DIR, path=file_path, message="目标是目录，无法写入",
                    ))
                if not overwrite:
                    return WriteResult(error=BackendError(
                        code=ErrorCode.ALREADY_EXISTS, path=file_path,
                        message="文件已存在，请用 edit() 修改或用 overwrite=True 覆盖",
                    ))

            parent_path2, filename = self._split_parent_and_name(norm, self.workspace_root.value)

            try:
                if is_update:
                    if existing.is_version_node:
                        await self._update_version_content(db, existing, content)
                    else:
                        await self._update_existing(db, existing, content)
                else:
                    await self._create_new_file(db, parent_path2, filename, content)
            except Exception as e:
                logger.exception("Write failed for '%s'", file_path)
                return WriteResult(error=BackendError(
                    code=ErrorCode.IO_ERROR, path=file_path, message=f"Write failed: {e}",
                ))

        return WriteResult(path=file_path)

    async def _update_existing(
        self, db: AsyncSession, node: _Resolved, content: str,
    ) -> None:
        res = await resource_crud.get_resource_with_versions(db, node.id)
        if res is None:
            raise ValueError(f"Resource {node.id} not found in DB")
        if res.itemType != ResourceItemType.RESOURCE.value:
            raise ValueError(f"Resource {node.id} is not a writable file")

        latest = res.latest_version

        if _is_direct_text_type(node.resource_type):
            existing_text = latest.content if latest else ""
            if content == existing_text:
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
        self, db: AsyncSession, node: _Resolved, content: str,
    ) -> None:
        version_id = _extract_version_id(node.id)

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
        self, db: AsyncSession, parent_path: str, filename: str, content: str,
    ) -> None:
        parent_id, new_folders = await self._ensure_parent_chain(db, parent_path)

        if filename == "SKILL.md" and new_folders:
            skill_folder_id = new_folders[-1]
            skill_folder = await resource_crud.get_resource(db, skill_folder_id)
            if skill_folder and skill_folder.resourceType != ResourceType.SKILL.value:
                skill_folder.resourceType = ResourceType.SKILL.value
                await db.commit()
                await db.refresh(skill_folder)

        fs = FileService(db)
        db_file = await fs.save_file_from_bytes(
            data=content.encode("utf-8"),
            filename=filename,
            mime_type="text/plain",
            management_type=["resource"],
            sub_path="resources",
        )

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
        self, db: AsyncSession, parent_path: str,
    ) -> tuple[str | None, list[str]]:
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

        first_seg = segments[0]
        if first_seg in self._shortcuts:
            shortcut_id = self._shortcuts[first_seg]
            shortcut_res = await resource_crud.get_resource(db, shortcut_id)
            if shortcut_res is None:
                raise ValueError(f"Shortcut resource {shortcut_id} not found")
            if shortcut_res.itemType != ResourceItemType.FOLDER.value:
                raise ValueError(f"Cannot create files under a non-folder shortcut '{first_seg}'")
            current_id = shortcut_id
            remaining = segments[1:]
        else:
            current_id = self._root_resource_id
            remaining = segments

        new_ids: list[str] = []
        for seg in remaining:
            existing = await resource_crud.get_resource_by_name_and_parent(db, seg, current_id)
            if existing:
                current_id = existing.id
                continue

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
    # Core: edit
    # ==================================================================

    def edit(
        self, file_path: VirtualPath, old_str: str, new_str: str, *,
        replace_all: bool = False,
    ) -> EditResult:
        return self._run_async(
            self._aedit_impl(file_path, old_str, new_str, replace_all=replace_all),
            EditResult,
        )

    async def aedit(
        self, file_path: VirtualPath, old_str: str, new_str: str, *,
        replace_all: bool = False,
    ) -> EditResult:
        async with self._lock:
            return await self._aedit_impl(file_path, old_str, new_str, replace_all=replace_all)

    async def _aedit_impl(
        self, file_path: VirtualPath, old_str: str, new_str: str, *,
        replace_all: bool = False,
    ) -> EditResult:
        if not old_str:
            return EditResult(error=BackendError(
                code=ErrorCode.INVALID, message="old_str 不能为空",
            ))
        try:
            norm = self._normalize_path(file_path)
        except BackendError as e:
            return EditResult(error=e)

        if not self._check_edit_allowed(norm):
            return EditResult(error=BackendError(
                code=ErrorCode.EDIT_NOT_ALLOWED, path=file_path, message="路径不允许编辑",
            ))

        read_res = await self._aread_raw_impl(file_path, limit=1_000_000)
        if read_res.error:
            return EditResult(error=read_res.error)
        current = read_res.content or ""

        old_str = old_str.replace("\r\n", "\n").replace("\r", "\n")
        new_str = new_str.replace("\r\n", "\n").replace("\r", "\n")

        occurrences = current.count(old_str)

        if occurrences == 0:
            trail_mismatch = detect_trailing_newline_mismatch(old_str, current)
            if trail_mismatch is not None:
                return trail_mismatch
            return EditResult(error=BackendError(
                code=ErrorCode.OLD_STR_NOT_FOUND, path=file_path,
                message="未找到要替换的文本，请先读文件确认内容",
            ))

        if occurrences > 1 and not replace_all:
            return EditResult(error=BackendError(
                code=ErrorCode.MULTI_OCCURRENCES, path=file_path,
                message=f"匹配到 {occurrences} 处，请用 replace_all=True 替换全部或提供更精确的上下文",
            ))

        new_content = current.replace(old_str, new_str, -1 if replace_all else 1)
        write_res = await self._awrite_impl(file_path, new_content, overwrite=True)
        if write_res.error:
            return EditResult(error=write_res.error)

        return EditResult(path=file_path, occurrences=occurrences)

    # ==================================================================
    # Core: grep
    # ==================================================================

    def grep(
        self, pattern: str, path: VirtualPath = VirtualPath("/workspace"),
        glob: str | None = None, regex: bool = True,
        offset: int = 0, limit: int | None = None,
    ) -> GrepResult:
        return self._run_async(
            self._agrep_impl(pattern, path, glob, regex, offset, limit),
            GrepResult,
        )

    async def agrep(
        self, pattern: str, path: VirtualPath = VirtualPath("/workspace"),
        glob: str | None = None, regex: bool = True,
        offset: int = 0, limit: int | None = None,
    ) -> GrepResult:
        async with self._lock:
            return await self._agrep_impl(pattern, path, glob, regex, offset, limit)

    async def _agrep_impl(
        self, pattern: str, path: VirtualPath, glob: str | None, regex: bool,
        offset: int, limit: int | None,
    ) -> GrepResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return GrepResult(error=e)

        compiled: re.Pattern | None = None
        if regex:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return GrepResult(error=BackendError(
                    code=ErrorCode.INVALID, message=f"无效正则: {e}",
                ))

        async with self._session_factory() as db:
            target = await self._resolve_resource(db, norm)
            if target is None:
                return GrepResult(error=BackendError(
                    code=ErrorCode.NOT_FOUND, path=path, message="路径不存在",
                ))
            if not target.is_dir:
                return await self._grep_single_file(db, target, norm, pattern, compiled, glob, offset, limit)

            if target.id == "__ws_root__":
                if not self._root_resource_id:
                    return GrepResult(matches=[])
                root_id = self._root_resource_id
            else:
                root_id = target.id

            pairs = await self._load_subtree_with_paths(db, root_id, norm)

            matches: list[GrepMatch] = []
            file_id_pairs: list[tuple[str, str, str]] = []  # (vpath, file_id, name)

            for vpath, res in pairs:
                if res.itemType != ResourceItemType.RESOURCE.value:
                    continue
                if glob is not None and not fnmatch.fnmatch(res.name, glob):
                    continue

                if _is_direct_text_type(res.resourceType):
                    lv = res.latest_version
                    content = lv.content if lv else ""
                    for li, line in enumerate(content.splitlines(), start=1):
                        if compiled is not None:
                            if compiled.search(line):
                                matches.append(GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000]))
                        else:
                            if pattern in line:
                                matches.append(GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000]))
                elif _is_file_id_type(res.resourceType) and res.latest_version and res.latest_version.content:
                    file_id_pairs.append((vpath, res.latest_version.content, res.name))

            # resolve file-id contents
            if file_id_pairs:
                fs = FileService(db)
                for vpath, fid, name in file_id_pairs:
                    try:
                        raw = await fs.get_file_content(fid)
                        content = raw.decode("utf-8")
                    except Exception:
                        continue
                    for li, line in enumerate(content.splitlines(), start=1):
                        if compiled is not None:
                            if compiled.search(line):
                                matches.append(GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000]))
                        else:
                            if pattern in line:
                                matches.append(GrepMatch(path=VirtualPath(vpath), line=li, text=line[:2000]))

        return self._apply_grep_limit(matches, offset, limit)

    async def _grep_single_file(
        self, db: AsyncSession, target: _Resolved, norm: str,
        pattern: str, compiled: re.Pattern | None, glob: str | None,
        offset: int, limit: int | None,
    ) -> GrepResult:
        matches: list[GrepMatch] = []
        if not target.resource_type:
            return self._apply_grep_limit(matches, offset, limit)

        if glob is not None and not fnmatch.fnmatch(target.name, glob):
            return self._apply_grep_limit(matches, offset, limit)

        if _is_direct_text_type(target.resource_type):
            content = target.content or ""
            for li, line in enumerate(content.splitlines(), start=1):
                if compiled is not None:
                    if compiled.search(line):
                        matches.append(GrepMatch(path=VirtualPath(norm), line=li, text=line[:2000]))
                else:
                    if pattern in line:
                        matches.append(GrepMatch(path=VirtualPath(norm), line=li, text=line[:2000]))
        elif _is_file_id_type(target.resource_type) and target.content:
            fs = FileService(db)
            try:
                raw = await fs.get_file_content(target.content)
                content = raw.decode("utf-8")
            except Exception:
                content = ""
            for li, line in enumerate(content.splitlines(), start=1):
                if compiled is not None:
                    if compiled.search(line):
                        matches.append(GrepMatch(path=VirtualPath(norm), line=li, text=line[:2000]))
                else:
                    if pattern in line:
                        matches.append(GrepMatch(path=VirtualPath(norm), line=li, text=line[:2000]))

        return self._apply_grep_limit(matches, offset, limit)

    # ==================================================================
    # Core: glob
    # ==================================================================

    def glob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        return self._run_async(self._aglob_impl(pattern, path), GlobResult)

    async def aglob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        async with self._lock:
            return await self._aglob_impl(pattern, path)

    async def _aglob_impl(self, pattern: str, path: VirtualPath) -> GlobResult:
        try:
            norm = self._normalize_path(path)
        except BackendError as e:
            return GlobResult(error=e)

        async with self._session_factory() as db:
            target = await self._resolve_resource(db, norm)
            if target is None:
                return GlobResult(error=BackendError(
                    code=ErrorCode.NOT_FOUND, path=path, message="路径不存在",
                ))
            if not target.is_dir:
                return GlobResult(error=BackendError(
                    code=ErrorCode.NOT_DIR, path=path, message="目标是文件，不是目录",
                ))

            if target.id == "__ws_root__":
                if not self._root_resource_id:
                    return GlobResult(matches=[])
                root_id = self._root_resource_id
            else:
                root_id = target.id

            pairs = await self._load_subtree_with_paths(db, root_id, norm)
            size_map = await self._resolve_file_sizes_batch(db, pairs)

            matched: list[FileInfo] = []
            for vpath, res in pairs:
                if not fnmatch_path(
                    vpath[len(norm.rstrip("/") + "/"):] if vpath != norm else "", pattern,
                ):
                    continue
                is_dir = res.itemType == ResourceItemType.FOLDER.value
                sz = 0
                modified = ""
                if not is_dir:
                    lv = res.latest_version
                    if lv:
                        if _is_direct_text_type(res.resourceType):
                            sz = len(lv.content or "")
                        else:
                            sz = size_map.get(vpath, 0)
                        if lv.updatedAt:
                            modified = lv.updatedAt.isoformat() if isinstance(lv.updatedAt, datetime) else str(lv.updatedAt)

                matched.append(FileInfo(
                    path=VirtualPath(vpath),
                    is_dir=is_dir,
                    size=sz,
                    modified_at=modified,
                    desc=getattr(res, "description", None) or "",
                ))

            matched.sort(key=lambda fi: fi.path)
            return GlobResult(matches=matched)

    # ==================================================================
    # Extra: ls_version
    # ==================================================================

    def ls_version(self, path: VirtualPath) -> LsVersionResult:
        return self._run_async(self._als_version_impl(path), LsVersionResult)

    async def als_version(self, path: VirtualPath) -> LsVersionResult:
        async with self._lock:
            return await self._als_version_impl(path)

    async def _als_version_impl(self, path: VirtualPath) -> LsVersionResult:
        try:
            raw = str(path)
        except Exception:
            raw = str(path)

        normalized = raw.rstrip("/")
        if not normalized.endswith(_VERSION_FOLDER_SUFFIX):
            normalized = normalized + _VERSION_FOLDER_SUFFIX

        try:
            norm = self._normalize_path(VirtualPath(normalized))
        except BackendError as e:
            return LsVersionResult(error=e)

        # Resolve the resource that owns the $v folder
        # Strip $v suffix to get the flat file path, then resolve
        flat_norm = norm
        if flat_norm.endswith(_VERSION_FOLDER_SUFFIX):
            flat_norm = flat_norm[:-len(_VERSION_FOLDER_SUFFIX)]
        if flat_norm.endswith("/"):
            flat_norm = flat_norm[:-1]

        async with self._session_factory() as db:
            resolved = await self._resolve_resource(db, flat_norm)
            if resolved is None:
                return LsVersionResult(error=BackendError(
                    code=ErrorCode.NOT_FOUND, path=VirtualPath(normalized),
                    message="未找到资源版本文件夹。请使用 ls 查找资源（版本文件夹以 '$v/' 结尾）。",
                ))

            res = await resource_crud.get_resource_with_versions(db, resolved.id)
            if res is None or not res.versions:
                return LsVersionResult(versions=[])

            active_version_id = res.latestVersionId
            version_infos: list[VersionInfo] = []
            folder_prefix = norm.rstrip("/") + "/"

            for ver in res.versions:
                is_active = (ver.id == active_version_id)
                ver_vpath = f"{folder_prefix}{ver.id}"

                version_infos.append(VersionInfo(
                    version_id=ver.id,
                    name=ver.name,
                    sort_order=ver.sortOrder,
                    is_active=is_active,
                    updated_at=ver.updatedAt.isoformat() if ver.updatedAt and isinstance(ver.updatedAt, datetime) else str(ver.updatedAt) if ver.updatedAt else "",
                    file_path=ver_vpath,
                ))

            version_infos.sort(key=lambda v: v.sort_order)
            return LsVersionResult(versions=version_infos) if version_infos else LsVersionResult(versions=[])

    # ==================================================================
    # Sync bridge
    # ==================================================================

    @staticmethod
    def _run_async(coro, result_cls: type):
        try:
            return asyncio.run(coro)
        except Exception as e:
            return _construct_error(result_cls, str(e))


# ==================================================================
# Helpers
# ==================================================================


def _build_virtual_path(
    res_id: str, res_name: str,
    parent_map: dict[str, str | None],
    name_map: dict[str, str],
    *,
    root_id: str,
    base_vpath: str,
) -> str | None:
    """Walk up parent chain to build a virtual path."""
    pid = parent_map.get(res_id)
    if pid == root_id:
        return f"{base_vpath}/{res_name}"

    parts: list[str] = [res_name]
    current = pid
    while current and current != root_id:
        name = name_map.get(current)
        if name is None:
            return None
        parts.append(name)
        current = parent_map.get(current)

    parts.reverse()
    return f"{base_vpath}/{posixpath.join(*parts)}"


def _build_tree_string(
    root_norm: str, entries_map: dict[str, _Resolved], depth: int,
) -> str:
    """Build a formatted tree string from a flat entries map."""
    sorted_paths = sorted(entries_map.keys())

    root_name = PurePosixPath(root_norm).name or root_norm.rstrip("/")
    tree_entries: list[TreeEntry] = [TreeEntry(name=root_name + "/", depth=0)]

    seen_dirs: set[str] = set()
    dir_has_visible_children: dict[str, bool] = {}

    for rel in sorted_paths:
        d = rel.count("/") + 1
        if d > depth:
            continue
        node = entries_map[rel]

        parts = PurePosixPath(rel).parts
        for i in range(1, len(parts)):
            parent_rel = str(PurePosixPath(*parts[:i]))
            if parent_rel not in seen_dirs:
                seen_dirs.add(parent_rel)
                dir_has_visible_children[parent_rel] = True

        if node.is_dir:
            seen_dirs.add(rel)

    dirs_to_show: dict[str, _Resolved] = {}
    for rel in sorted_paths:
        d = rel.count("/") + 1
        if d > depth:
            continue
        node = entries_map[rel]
        if node.is_dir and d <= depth:
            dirs_to_show[rel] = node
            has_kids = any(
                other.startswith(rel + "/") and other != rel
                for other in sorted_paths
            )
            dir_has_visible_children[rel] = has_kids

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

        sorted_entries.append((rel + "/", TreeEntry(
            name=PurePosixPath(rel).name + "/", depth=d, marker=marker,
        )))

    for rel in sorted_paths:
        d = rel.count("/") + 1
        if d > depth:
            continue
        node = entries_map[rel]
        if node.is_dir:
            continue
        size_str = human_size(node.size)
        sorted_entries.append((rel, TreeEntry(
            name=f"{PurePosixPath(rel).name} ({size_str})", depth=d,
        )))

    sorted_entries.sort(key=lambda x: x[0])
    tree_entries.extend(e[1] for e in sorted_entries)

    return format_tree_entries(tree_entries)


def _construct_error(result_cls: type, msg: str):
    try:
        return result_cls(error=BackendError(code=ErrorCode.IO_ERROR, message=msg))
    except Exception:
        return result_cls()
