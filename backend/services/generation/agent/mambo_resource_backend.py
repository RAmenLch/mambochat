# backend/services/generation/agent/mambo_resource_backend.py

"""Resource-tree backend for mambo_agents.

Maps the Resource DB tree (folders + typed resources) to the
``BackendProtocol`` virtual filesystem.  A single folder-type
Resource serves as the workspace root; its descendant sub-tree
is loaded into an in-memory cache for fast path resolution.

Content semantics by ResourceType:

* FOLDER (any)          → directory, no content
* FILE / KB_FILE        → content is a file_id, resolved via FileService
* SYSTEM_PROMPT         → content is the raw text (direct text type)
* SUBMESSAGE_TEMPLATE   → content is the raw text (direct text type)

Safety invariants
=================
* Never write content into a FOLDER node
* Workspace boundary enforced on every path
* Path traversal (``..``) rejected
* Edit whitelist/blacklist (fnmatch on filename) gate all writes
* New files are always created as ResourceType.FILE
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
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

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
    WorkspacePathError,
    WriteResult,
    _get_file_type,
    _get_mime_type,
)
from mambo_agents.backends.utils import (
    detect_trailing_newline_mismatch,
    format_with_line_numbers,
)

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

    def __init__(
        self,
        resource_id: str | None,
        session_factory: Callable[[], AsyncSession],
        *,
        shortcuts: dict[str, str] | None = None,
        workspace_root: str = "/workspace",
        edit_whitelist: frozenset[str] | None = None,
        edit_blacklist: frozenset[str] | None = None,
        max_read_chars: int = 100_000,
        summarizer: ReadSummarizer | None = None,
    ) -> None:
        super().__init__(max_read_chars=max_read_chars, summarizer=summarizer)

        if edit_whitelist is not None and edit_blacklist is not None:
            raise ValueError(
                "edit_whitelist and edit_blacklist are mutually exclusive."
            )

        self.workspace_root = workspace_root.rstrip("/")
        self._root_resource_id = resource_id
        self._shortcuts: dict[str, str] = shortcuts or {}
        self._session_factory = session_factory
        self._edit_whitelist = edit_whitelist or frozenset()
        self._edit_blacklist = edit_blacklist or frozenset()
        self._lock = asyncio.Lock()

        self._cache: dict[str, _CachedNode] = {}
        self._load_subtree()

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list:
        return []

    @property
    def description(self) -> str:
        wr = self.workspace_root
        parts: list[str] = []
        if self._root_resource_id:
            parts.append(f"Rooted at resource '{self._root_resource_id}'")
        if self._shortcuts:
            sc_keys = ", ".join(f"'{k}'" for k in self._shortcuts)
            parts.append(f"Shortcuts: {sc_keys}")
        return (
            f"Resource-tree backend. {'; '.join(parts)} "
            f"All file paths must be under '{wr}'. "
            "The read tool defaults to no line numbers. "
            "Set include_line_numbers=True when you need to reference "
            "specific lines."
        )

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
                    cache[self.workspace_root] = _resource_to_node(root_res)
                    await self._load_subtree_into_cache(
                        cache, db, self._root_resource_id, self.workspace_root
                    )

            # --- 2. Shortcut mappings ---
            await self._load_shortcuts_into_cache(cache, db)

        self._cache = cache

    async def _load_subtree_into_cache(
        self,
        cache: dict[str, _CachedNode],
        db: AsyncSession,
        root_id: str,
        base_vpath: str,
    ) -> None:
        """Load all descendants of *root_id* and populate *cache*
        with virtual paths rooted at *base_vpath*."""
        descendants = await self._load_descendants(db, root_id)
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
            if virt:
                cache[virt] = _resource_to_node(res)

    async def _load_shortcuts_into_cache(
        self,
        cache: dict[str, _CachedNode],
        db: AsyncSession,
    ) -> None:
        """Mount shortcut resources directly at ``{workspace_root}/{name}``.

        Each shortcut maps a virtual name to a single resource ID.
        Folder resources are expanded in-place (no extra nesting).
        """
        for name, res_id in self._shortcuts.items():
            vpath = f"{self.workspace_root}/{name}"

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
            else:
                # 文件资源挂载为 shortcut 路径下的单个文件
                cache[vpath] = _resource_to_node(res)

    async def _load_descendants(
        self, db: AsyncSession, root_id: str | None = None
    ) -> list[resource_model.Resource]:
        """CTE-recursive: load all descendants under *root_id*.

        If *root_id* is omitted, defaults to ``self._root_resource_id``.
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

        stmt = (
            select(resource_model.Resource)
            .options(joinedload(resource_model.Resource.latest_version))
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
        base = base_vpath or self.workspace_root

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

    def _normalize_path(self, path: str) -> str:
        """Ensure path starts with workspace_root; reject traversals."""
        if not path.startswith("/"):
            path = "/" + path
        norm = posixpath.normpath(path)

        wr = self.workspace_root
        if norm != wr and not norm.startswith(wr + "/"):
            raise WorkspacePathError(
                f"Path '{path}' is outside the workspace. "
                f"All file paths must be under '{wr}'."
            )

        if ".." in PurePosixPath(path).parts:
            raise WorkspacePathError(
                f"Path '{path}' contains '..' which is not allowed."
            )

        return norm

    def _resolve(self, path: str) -> _CachedNode | None:
        """Resolve a virtual path to a cached node."""
        try:
            norm = self._normalize_path(path)
        except WorkspacePathError:
            return None
        return self._cache.get(norm)

    def _check_edit_allowed(self, path: str) -> bool:
        """Gate writes by filename whitelist/blacklist (fnmatch)."""
        filename = PurePosixPath(path).name
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

    def ls(self, path: str) -> LsResult:
        return self._sync_bridge(_LsResult, self._als_impl, path)

    async def als(self, path: str) -> LsResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._als_impl(path)

    async def _als_impl(self, path: str) -> LsResult:
        try:
            norm = self._normalize_path(path)
        except WorkspacePathError as e:
            return LsResult(error=str(e))

        entries: list[FileInfo] = []
        prefix = norm.rstrip("/") + "/"

        for vpath, node in self._cache.items():
            if vpath == norm:
                continue
            if not vpath.startswith(prefix):
                continue
            # Must be a direct child (no intermediate '/')
            rel = vpath[len(prefix):]
            if "/" in rel:
                continue

            entries.append(FileInfo(
                path=vpath + ("/" if node.is_dir else ""),
                is_dir=node.is_dir,
                size=node.size,
                modified_at=node.modified_at,
                desc=node.desc,
            ))

        entries.sort(key=lambda fi: (not fi.is_dir, fi.path))
        return LsResult(entries=entries) if entries else LsResult(entries=[])

    # ==================================================================
    # Core: read  (async-first: _aread_raw_impl)
    # ==================================================================

    def read_raw(
        self,
        file_path: str,
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
        file_path: str,
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
        file_path: str,
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
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        try:
            norm = self._normalize_path(file_path)
        except WorkspacePathError as e:
            return ReadResult(error=str(e))

        node = self._resolve(norm)
        if node is None:
            return ReadResult(error=f"File '{file_path}' not found")
        if node.is_dir:
            return ReadResult(error=f"'{file_path}' is a directory")

        # ---- fetch text content ----
        text: str
        try:
            if _is_file_id_type(node.resource_type):
                text = await self._read_file_id_content(node)
            else:
                text = node.content or ""
        except Exception as e:
            return ReadResult(
                content="",
                total_lines=0,
                encoding="utf-8",
                file_type=_get_file_type(file_path),
                mime_type=_get_mime_type(file_path),
                error=f"Error reading '{file_path}': {e}",
            )

        # ---- apply offset / limit / line numbers ----
        lines = text.splitlines(keepends=True)
        total = len(lines)

        if total > 0 and offset >= total:
            return ReadResult(
                error=f"Line offset {offset} exceeds file length ({total} lines)"
            )

        sliced = lines[offset: offset + limit]
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

    # ==================================================================
    # Core: write  (async-first: _awrite_impl)
    # ==================================================================

    def write(
        self, file_path: str, content: str, overwrite: bool = False,
    ) -> WriteResult:
        return self._sync_bridge(
            _WriteResult, self._awrite_impl, file_path, content, overwrite,
        )

    async def awrite(
        self, file_path: str, content: str, overwrite: bool = False,
    ) -> WriteResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._awrite_impl(file_path, content, overwrite)

    async def _awrite_impl(
        self, file_path: str, content: str, overwrite: bool = False,
    ) -> WriteResult:
        # 1. Validate
        try:
            norm = self._normalize_path(file_path)
        except WorkspacePathError as e:
            return WriteResult(error=str(e))

        if not self._check_edit_allowed(norm):
            return WriteResult(
                error=f"Path '{file_path}' is not allowed for write. "
                       "Check edit_whitelist / edit_blacklist."
            )

        parent_path, filename = self._split_parent_and_name(
            norm, self.workspace_root
        )

        # 2. Check target
        existing = self._resolve(norm)
        is_update = existing is not None

        if is_update:
            # SAFETY: refuse to write content into a folder
            if existing.is_dir:
                return WriteResult(
                    error=f"Cannot write '{file_path}': it is a folder, not a file."
                )
            if not overwrite:
                return WriteResult(
                    error=f"Cannot write '{file_path}': file exists. "
                           "Use overwrite=True to replace."
                )

        # 3. Perform write
        try:
            async with self._session_factory() as db:
                if is_update:
                    await self._update_existing(db, norm, existing, content)
                else:
                    await self._create_new_file(db, parent_path, filename, content)
        except Exception as e:
            logger.exception("Write failed for '%s'", file_path)
            return WriteResult(error=f"Write failed: {e}")

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

        if parent_path == self.workspace_root:
            return self._root_resource_id, []

        rel = parent_path[len(self.workspace_root):].lstrip("/")
        segments = [s for s in rel.split("/") if s]
        if not segments:
            return self._root_resource_id, []

        current_id: str | None = self._root_resource_id
        new_ids: list[str] = []

        for i, seg in enumerate(segments):
            target_vpath = (
                f"{self.workspace_root}/{'/'.join(segments[: i + 1])}"
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
        file_path: str,
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
        file_path: str,
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
        file_path: str,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        # 1. Validate
        try:
            norm = self._normalize_path(file_path)
        except WorkspacePathError as e:
            return EditResult(error=str(e))

        if not self._check_edit_allowed(norm):
            return EditResult(
                error=f"Path '{file_path}' is not allowed for edit. "
                       "Check edit_whitelist / edit_blacklist."
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
                file_path, old_str, current,
            )
            if trail_mismatch is not None:
                return trail_mismatch
            return EditResult(
                error=f"Cannot edit '{file_path}': old_str not found in file. "
                       "Read the file first to see its exact content."
            )

        if occurrences > 1 and not replace_all:
            return EditResult(
                error=f"Cannot edit '{file_path}': old_str appears "
                       f"{occurrences} times. Use replace_all=True."
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
        path: str = "/workspace",
        glob: str | None = None,
        regex: bool = False,
    ) -> GrepResult:
        """Grep files under *path*.  Direct-text nodes are matched synchronously
        without any DB I/O; only file-id nodes (FILE / KB_FILE) go through
        the async bridge — and even then, concurrently via ``asyncio.gather``
        rather than one-at-a-time."""
        try:
            norm = self._normalize_path(path)
        except WorkspacePathError as e:
            return GrepResult(error=str(e))

        prefix = norm.rstrip("/") + "/"

        compiled: re.Pattern | None = None
        if regex:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return GrepResult(error=f"Invalid regex pattern: {e}")

        matches: list[GrepMatch] = []

        # --- Phase 1 (sync): grep direct-text nodes inline — zero DB, zero blocking ---
        file_id_pairs: list[tuple[str, str]] = []  # (vpath, node_id)
        for vpath, node in self._cache.items():
            if node.is_dir:
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
                                GrepMatch(path=vpath, line=li, text=line[:2000])
                            )
                    else:
                        if pattern in line:
                            matches.append(
                                GrepMatch(path=vpath, line=li, text=line[:2000])
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

        return GrepResult(matches=matches)

    async def _grep_file_id_nodes(
        self,
        pairs: list[tuple[str, str]],
        compiled: re.Pattern | None,
        pattern: str,
    ) -> GrepResult:
        """Async helper: concurrently read + grep file-id nodes.
        Called from ``_sync_bridge`` inside a worker-thread event loop."""
        reads = [
            self._aread_raw_impl(vpath, limit=500_000)
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
                            GrepMatch(path=vpath, line=li, text=line[:2000])
                        )
                else:
                    if pattern in line:
                        matches.append(
                            GrepMatch(path=vpath, line=li, text=line[:2000])
                        )

        return GrepResult(matches=matches)

    async def agrep(
        self,
        pattern: str,
        path: str = "/workspace",
        glob: str | None = None,
        regex: bool = False,
    ) -> GrepResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._agrep_impl(pattern, path, glob, regex)

    async def _agrep_impl(
        self,
        pattern: str,
        path: str = "/workspace",
        glob: str | None = None,
        regex: bool = False,
    ) -> GrepResult:
        try:
            norm = self._normalize_path(path)
        except WorkspacePathError as e:
            return GrepResult(error=str(e))

        prefix = norm.rstrip("/") + "/"

        compiled: re.Pattern | None = None
        if regex:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                return GrepResult(error=f"Invalid regex pattern: {e}")

        matches: list[GrepMatch] = []

        # --- Phase 1 (sync): grep direct-text nodes inline — zero DB calls ---
        file_id_pairs: list[tuple[str, str]] = []
        for vpath, node in self._cache.items():
            if node.is_dir:
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
                                GrepMatch(path=vpath, line=li, text=line[:2000])
                            )
                    else:
                        if pattern in line:
                            matches.append(
                                GrepMatch(path=vpath, line=li, text=line[:2000])
                            )
            elif _is_file_id_type(node.resource_type):
                file_id_pairs.append((vpath, node.id))

        # --- Phase 2 (async): grep file-id nodes concurrently ---
        if file_id_pairs:
            result = await self._grep_file_id_nodes(file_id_pairs, compiled, pattern)
            if result.matches:
                matches.extend(result.matches)

        return GrepResult(matches=matches)

    # ==================================================================
    # Core: glob  (async-first: _aglob_impl)
    # ==================================================================

    def glob(self, pattern: str, path: str = "/workspace") -> GlobResult:
        return self._sync_bridge(
            _GlobResult, self._aglob_impl, pattern, path,
        )

    async def aglob(self, pattern: str, path: str = "/workspace") -> GlobResult:
        """Override parent: call async impl directly, serialized via lock."""
        async with self._lock:
            return await self._aglob_impl(pattern, path)

    async def _aglob_impl(
        self, pattern: str, path: str = "/workspace",
    ) -> GlobResult:
        try:
            norm = self._normalize_path(path)
        except WorkspacePathError as e:
            return GlobResult(error=str(e))

        prefix = norm.rstrip("/") + "/"

        matched: list[FileInfo] = []
        for vpath, node in self._cache.items():
            if node.is_dir:
                continue
            if vpath != norm and not vpath.startswith(prefix):
                continue
            if not fnmatch.fnmatch(node.name, pattern):
                continue
            matched.append(FileInfo(
                path=vpath,
                is_dir=False,
                size=node.size,
                modified_at=node.modified_at,
                desc=node.desc,
            ))

        matched.sort(key=lambda fi: fi.path)
        return GlobResult(matches=matched)

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
        return result_cls(error=msg)
    except Exception:
        # Fallback for result types without 'error' field
        return result_cls()


# Type aliases to pass class objects around
_LsResult = LsResult
_ReadResult = ReadResult
_WriteResult = WriteResult
_EditResult = EditResult
_GrepResult = GrepResult
_GlobResult = GlobResult
