# backend/services/generation/agent/mambo_api_backend.py

"""API Backend for Mambo Agents.

Provides filesystem access via a WebSocket-connected client, implementing
``mambo_agents.backends.protocol.BackendProtocol``.

The client actively connects to the MamboChat server's WebSocket endpoint.
This backend sends file operation commands through the WebSocket and waits
for the client to execute them and return results.

Unlike the deepagents version, this returns mambo_agents-style result types
(LsResult, ReadResult, WriteResult, etc.) instead of deepagents-style types.

The WebSocket client implementation lives at:
    desktop/src/main/apiClient.ts
"""

import base64
import logging
import posixpath
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from mambo_agents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    DownloadFileResult,
    EditResult,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    UploadFileResult,
    VirtualPath,
    WriteResult,
)
from mambo_agents.backends.schemas import BackendError, ErrorCode, VirtualPathArg
from mambo_agents.backends.utils.multimodal import get_file_type, get_mime_type

logger = logging.getLogger(__name__)


class MamboAPIBackend(BackendProtocol):
    """Backend that proxies file operations to a WebSocket-connected client.

    The client connects to the server's WebSocket endpoint at::

        ws://server/api/api-client/ws/{backend_id}?api_key=xxx

    All file operations are sent as JSON commands through the WebSocket
    and results are returned by the client.  The server passes virtual
    paths directly to the client, which resolves them relative to its
    own root directory.

    Also supports shell command execution via the client's subprocess
    when the remote client advertises the ``execute`` capability.
    """

    def __init__(
        self,
        backend_id: str,
        backend_name: str = "",
        edit_whitelist: list[str] | None = None,
        edit_blacklist: list[str] | None = None,
        ignore_dirs: list[str] | None = None,
        timeout: float = 60.0,
        enable_execute: bool = False,
        execute_timeout: int = 180,
        max_read_chars: int = 100_000,
        max_grep_matches: int = 1000,
    ) -> None:
        super().__init__(
            max_read_chars=max_read_chars,
            max_grep_matches=max_grep_matches,
        )
        self.backend_id = backend_id
        self.backend_name = backend_name or backend_id
        self.edit_whitelist = edit_whitelist or []
        self.edit_blacklist = edit_blacklist or []
        self.ignore_dirs = ignore_dirs or []
        self.timeout = timeout
        self._enable_execute = enable_execute
        self._execute_timeout = execute_timeout

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return f"api://{self.backend_name}"

    @property
    def tools(self) -> list[StructuredTool]:
        """Extra tools exposed by this backend beyond the core six."""
        tools: list[StructuredTool] = []
        tools.append(
            StructuredTool(
                name="tree",
                description=(
                    "View the directory tree structure. Shows directories and files "
                    "with their sizes in a tree format.\n\n"
                    "Args:\n"
                    "  path: Root directory to display (default: /workspace).\n"
                    "  depth: Maximum recursion depth (default: 3, must be >= 1)."
                ),
                args_schema=create_model(
                    "TreeSchema",
                    path=(VirtualPathArg, Field(default=VirtualPath("/workspace"), description="Root directory to display")),
                    depth=(int, Field(default=3, description="Maximum recursion depth")),
                ),
                coroutine=self.atree,
            )
        )
        tools.append(
            StructuredTool(
                name="delete",
                description=(
                    "Delete a single file. Directories are NOT supported — "
                    "remove files inside the directory first, then the empty "
                    "directory disappears naturally."
                ),
                args_schema=create_model(
                    "DeleteSchema",
                    path=(VirtualPathArg, Field(description="Absolute file path to delete")),
                ),
                coroutine=self.adelete,
            )
        )
        if self._enable_execute:
            info = self._client_env()
            platform = info.get("platform", "")
            root_dir = info.get("root_dir", "")
            root_display = root_dir or "(real root directory)"
            wr = self.workspace_root.value
            tools.append(
                StructuredTool(
                    name="execute",
                    description=(
                        "Execute a shell command on the remote client machine. "
                        f"On Windows, commands run via cmd /c. "
                        f"On Linux/macOS, commands run via sh -c. "
                        "Returns combined stdout and stderr output.\n\n"
                        f"**CRITICAL — Real vs. virtual path mapping:** "
                        f"The workspace root `{wr}` is a virtual path that maps "
                        f"to the real directory `{root_display}`. "
                        f"File tools (ls/read/write/edit/grep/glob) accept "
                        f"`{wr}/...` virtual paths, but shell commands "
                        f"in **execute** run directly on the client's real "
                        f"filesystem. You MUST use real filesystem paths (e.g. "
                        f"`{root_display}/src/main.py`) in commands — "
                        f"virtual paths like `{wr}/src/main.py` do NOT exist "
                        f"on the client filesystem and will fail."
                    ),
                    args_schema=create_model(
                        "ExecuteSchema",
                        command=(str, Field(description="Shell command to execute")),
                        timeout=(int | None, Field(default=None, description="Optional timeout in seconds")),
                    ),
                    coroutine=self.aexecute,
                )
            )
        return tools

    @property
    def path_mapping_info(self) -> dict[str, str]:
        """Virtual ↔ real path mapping for the review agent's system prompt."""
        info = self._client_env()
        root = info.get("root_dir") or "(未知)"
        wr = self.workspace_root.value
        return {
            "workspace_root": wr,
            "real_root": root,
            "virtual_prefixes": "",
            "path_mapping": (
                f"\n- 虚拟路径 `{wr}/` → 真实路径 `{root}/`"
                if info.get("root_dir") else ""
            ),
        }

    @property
    def description(self) -> str:
        info = self._client_env()
        platform = info.get("platform", "")
        root_dir = info.get("root_dir", "")
        hostname = info.get("hostname", "")
        os_label = {"win32": "Windows", "darwin": "macOS"}.get(platform, platform or "")
        shell = "cmd /c" if platform == "win32" else ("sh -c" if platform else "platform-dependent")
        wr = self.workspace_root.value

        env_desc = (
            f"API-connected remote {os_label} filesystem"
            if os_label else "API-connected remote filesystem"
        )
        desc = (
            f"**Environment:** {env_desc} "
            f"(backend: '{self.backend_name}'"
            + (f", hostname: {hostname}" if hostname else "")
            + (f", working directory: {root_dir}" if root_dir else "")
            + f", shell: {shell}).\n"
            f"**Path mapping:** the workspace root `{wr}` maps to the real "
            f"directory `{root_dir or '(未知)'}` — all file tools must use paths under "
            f"`{wr}`. Paths outside `{wr}` (including `/`) are rejected."
        )
        if self._enable_execute:
            desc += (
                f"\n**execute tool:** shell commands run in `{root_dir or '(real root)'}`. "
                f"Use real filesystem paths in commands, NOT `{wr}` paths — "
                f"the virtual workspace path does not exist on the real filesystem."
            )
            if platform == "win32":
                desc += (
                    "\n**Windows quoting rules:** cmd.exe has no single-quote "
                    "support and no backslash escaping (unlike bash). "
                    "``python -c \"print('x')\"`` works — double quotes outside, "
                    "single quotes inside the code. But "
                    "``python -c 'print(\"x\")'`` (single-quoted delimiter) "
                    "fails silently (exit 0, no output). For anything non-trivial, "
                    "prefer writing a temporary script file with the write tool, "
                    "then executing it."
                )
        else:
            desc += " [shell execution disabled]"
        desc += (
            "\nThe read tool defaults to no line numbers. "
            "Set include_line_numbers=True when you need to reference specific lines."
        )
        return desc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client_env(self) -> dict:
        """Environment info reported by the connected API client ({} if unknown)."""
        try:
            from backend.routers.api_client_router import get_client_info

            return get_client_info(self.backend_id)
        except Exception:
            return {}

    def _check_online(self) -> str | None:
        """Check if the API client is currently connected.

        Returns None if online, otherwise an error message string.
        """
        from backend.routers.api_client_router import get_client_connection

        if get_client_connection(self.backend_id) is None:
            return (
                f'Backend "{self.backend_name}" 当前不在线。'
                f"请确认 API 客户端已启动并成功连接到服务器后再试。"
            )
        return None

    async def _call(self, method: str, params: dict, timeout: float | None = None) -> dict:
        """Send a command to the client via WebSocket and wait for response.

        Args:
            method: Command method name.
            params: Command parameters.
            timeout: Optional override for the WebSocket round-trip timeout.
                If None, falls back to ``self.timeout``.
        """
        offline_msg = self._check_online()
        if offline_msg:
            raise ConnectionError(offline_msg)

        from backend.routers.api_client_router import send_command

        logger.info("[API_BACKEND] _call: method=%s params=%s backend_id=%s", method, params, self.backend_id)
        result = await send_command(
            self.backend_id, method, params, timeout=timeout if timeout is not None else self.timeout
        )
        logger.info("[API_BACKEND] _call: method=%s got result keys=%s", method, list(result.keys()) if isinstance(result, dict) else type(result))
        return result

    def _normalize_path(self, virtual_path: VirtualPath) -> str:
        """Normalize a virtual path: ensure leading /, prevent traversal.

        Accepts VirtualPath (preferred) or str (backward-compat).
        Returns a plain string for use as cache key / WS params.
        """
        if not isinstance(virtual_path, VirtualPath):
            virtual_path = VirtualPath(virtual_path)
        raw = virtual_path.value
        norm = posixpath.normpath(raw)
        if norm.startswith(".."):
            raise ValueError("Path traversal not allowed.")
        return norm

    def _check_edit_permission(self, virtual_path: VirtualPath) -> None:
        """Check if *virtual_path* is allowed for write/edit via path prefix matching.

        Whitelist/blacklist entries are virtual path prefixes (e.g. ``"/workspace/src/"``).
        A path is allowed if it starts with (or equals) a whitelist prefix,
        or does NOT start with any blacklist prefix.
        """
        path_str = str(virtual_path)
        if self.edit_whitelist:
            allowed = any(
                path_str == p.rstrip("/") or path_str.startswith(p.rstrip("/") + "/")
                for p in self.edit_whitelist
            )
            if not allowed:
                raise PermissionError(
                    f"Edit denied: Path '{path_str}' is not in the edit whitelist."
                )
        if self.edit_blacklist:
            forbidden = any(
                path_str == p.rstrip("/") or path_str.startswith(p.rstrip("/") + "/")
                for p in self.edit_blacklist
            )
            if forbidden:
                raise PermissionError(
                    f"Edit denied: Path '{path_str}' is in the edit blacklist."
                )

    # Error code mapping from API client to BackendError
    _ERROR_CODE_MAP: dict[str, ErrorCode] = {
        "NOT_FOUND": ErrorCode.NOT_FOUND,
        "NOT_DIR": ErrorCode.NOT_DIR,
        "IS_DIR": ErrorCode.IS_DIR,
        "INVALID": ErrorCode.INVALID,
        "ALREADY_EXISTS": ErrorCode.ALREADY_EXISTS,
        "OLD_STR_NOT_FOUND": ErrorCode.OLD_STR_NOT_FOUND,
        "MULTI_OCCURRENCES": ErrorCode.MULTI_OCCURRENCES,
        "EDIT_NOT_ALLOWED": ErrorCode.EDIT_NOT_ALLOWED,
        "PATH_TRAVERSAL": ErrorCode.PATH_TRAVERSAL,
        "IO_ERROR": ErrorCode.IO_ERROR,
        "UNKNOWN_METHOD": ErrorCode.INVALID,
    }

    def _map_error(
        self,
        result: dict,
        path: VirtualPath | None = None,
        default_code: ErrorCode = ErrorCode.IO_ERROR,
    ) -> BackendError:
        """Map an API client error response to a BackendError with correct ErrorCode."""
        error_code = result.get("error_code", "")
        message = result.get("error", "Unknown error")
        code = self._ERROR_CODE_MAP.get(error_code, default_code)
        return BackendError(code=code, path=path, message=message)

    async def _run_ws_call(
        self,
        operation: str,
        fn,
        *args,
        **kwargs,
    ):
        """Shared pattern: run fn(...), catch ConnectionError/TimeoutError."""
        logger.info("[API_BACKEND] _run_ws_call START operation=%s", operation)
        try:
            result = await fn(*args, **kwargs)
            logger.info("[API_BACKEND] _run_ws_call DONE operation=%s", operation)
            return result
        except (ConnectionError, TimeoutError) as e:
            logger.error("[API_BACKEND] _run_ws_call %s failed: %s (%s)", operation, e, type(e).__name__)
            return None
        except Exception as e:
            logger.error("[API_BACKEND] _run_ws_call %s UNEXPECTED: %s (%s)", operation, e, type(e).__name__)
            return None

    # ------------------------------------------------------------------
    # Sync wrappers — delegate to async via asyncio.run()
    # ------------------------------------------------------------------

    @staticmethod
    def _run_sync(coro):
        """Run a coroutine synchronously. Safe to call from any thread
        that does NOT have a running event loop."""
        import asyncio
        return asyncio.run(coro)

    def _ls_sync(self, path: VirtualPath) -> LsResult:
        try:
            return self._run_sync(self.als(path))
        except Exception as e:
            return LsResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    def ls(self, path: VirtualPath) -> LsResult:
        return self._ls_sync(path)

    async def als(self, path: VirtualPath) -> LsResult:
        norm = self._normalize_path(path)
        result = await self._run_ws_call("ls", self._call, "ls", {"path": norm})
        if result is None:
            return LsResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))

        if result.get("error"):
            return LsResult(error=self._map_error(result, path=path))

        data = result.get("items", [])
        entries = []
        from mambo_agents.backends.protocol import FileInfo

        for item in data:
            path_raw = item.get("path", "/")
            path_clean = path_raw
            entries.append(
                FileInfo(
                    path=VirtualPath(path_clean),
                    is_dir=item.get("is_dir", False),
                    size=item.get("size", 0),
                    modified_at=item.get("modified_at", ""),
                )
            )
        return LsResult(entries=entries)

    def _read_sync(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int | None = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        try:
            return self._run_sync(self.aread_raw(file_path, offset, limit, include_line_numbers))
        except Exception as e:
            return ReadResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    def read_raw(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int | None = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        return self._read_sync(file_path, offset, limit, include_line_numbers)

    async def aread_raw(
        self,
        file_path: VirtualPath,
        offset: int = 0,
        limit: int | None = 2000,
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
                message=f"limit must be >= 1, got {limit}",
            ))
        norm = self._normalize_path(file_path)
        result = await self._run_ws_call(
            "read", self._call, "read_file",
            {"path": norm, "offset": offset, "limit": limit, "include_line_numbers": include_line_numbers},
        )
        if result is None:
            return ReadResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))

        if result.get("error"):
            return ReadResult(error=self._map_error(result, path=file_path))

        content = result.get("content", "")
        encoding = result.get("encoding", "utf-8")
        file_type = get_file_type(norm)
        mime_type = result.get("mime_type", "") or get_mime_type(norm)
        total_lines = result.get("total_lines", 0)

        if encoding == "base64":
            return ReadResult(
                content=content,
                total_lines=total_lines,
                encoding="base64",
                file_type=file_type,
                mime_type=mime_type,
            )

        lines = result.get("lines")
        # 若桌面端已在源头截断（truncated=true），优先采用截断后的 content，
        # 避免用未截断的 lines 重建而绕过限长。
        if lines is not None and not result.get("truncated"):
            content = "\n".join(lines)

        total = content.count("\n") + 1 if content else 0
        return ReadResult(content=content, total_lines=total, encoding="utf-8")

    def write(
        self, file_path: VirtualPath, content: str, overwrite: bool = False
    ) -> WriteResult:
        try:
            return self._run_sync(self.awrite(file_path, content, overwrite))
        except Exception as e:
            return WriteResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    async def awrite(
        self, file_path: VirtualPath, content: str, overwrite: bool = False
    ) -> WriteResult:
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return WriteResult(error=BackendError(
                code=ErrorCode.EDIT_NOT_ALLOWED,
                path=file_path,
                message=str(e),
            ))
        if get_file_type(file_path) != "text":
            return WriteResult(error=BackendError(
                code=ErrorCode.INVALID, path=file_path,
                message="无法写入该文件，非文本文件仅支持读取",
            ))

        norm = self._normalize_path(file_path)
        result = await self._run_ws_call(
            "write",
            self._call,
            "write_file",
            {"path": norm, "content": content, "overwrite": overwrite},
        )
        if result is None:
            return WriteResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))
        if result.get("error"):
            return WriteResult(error=self._map_error(result))
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: VirtualPath,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            return self._run_sync(self.aedit(file_path, old_str, new_str, replace_all=replace_all))
        except Exception as e:
            return EditResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    async def aedit(
        self,
        file_path: VirtualPath,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        if not old_str:
            return EditResult(error=BackendError(
                code=ErrorCode.INVALID, message="old_str 不能为空",
            ))
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return EditResult(error=BackendError(
                code=ErrorCode.EDIT_NOT_ALLOWED,
                path=file_path,
                message=str(e),
            ))
        if get_file_type(file_path) != "text":
            return EditResult(error=BackendError(
                code=ErrorCode.INVALID, path=file_path,
                message="无法编辑该文件，非文本文件仅支持读取",
            ))

        norm = self._normalize_path(file_path)
        result = await self._run_ws_call(
            "edit",
            self._call,
            "edit_file",
            {
                "path": norm,
                "old_string": old_str,
                "new_string": new_str,
                "replace_all": replace_all,
            },
        )
        if result is None:
            return EditResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))
        if result.get("error"):
            return EditResult(error=self._map_error(result, path=file_path))
        return EditResult(
            path=file_path,
            occurrences=result.get("occurrences", 0),
        )

    def grep(
        self, pattern: str, path: VirtualPath = VirtualPath("/workspace"), glob: str | None = None,
        regex: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> GrepResult:
        try:
            return self._run_sync(self.agrep(pattern, path, glob, regex, offset, limit))
        except Exception as e:
            return GrepResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    async def agrep(
        self, pattern: str, path: VirtualPath = VirtualPath("/workspace"), glob: str | None = None,
        regex: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> GrepResult:
        search_path = self._normalize_path(path) if path else "/"
        result = await self._run_ws_call(
            "grep",
            self._call,
            "grep_files",
            {"pattern": pattern, "path": search_path, "glob": glob, "regex": regex,
             "offset": offset, "limit": limit, "ignore_dirs": self.ignore_dirs},
        )
        if result is None:
            return GrepResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))
        if isinstance(result, dict) and result.get("error"):
            return GrepResult(error=self._map_error(result))
        data = result.get("matches", [])
        truncated = result.get("truncated", False) if isinstance(result, dict) else False
        total_matches = result.get("total", len(data)) if isinstance(result, dict) else 0
        matches: list[GrepMatch] = []
        for m in data:
            matches.append(
                GrepMatch(
                    path=VirtualPath(m.get("path", "/")),
                    line=m.get("line", 0),
                    text=m.get("text", ""),
                )
            )
        return GrepResult(matches=matches, truncated=truncated, total_matches=total_matches)

    def glob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        try:
            return self._run_sync(self.aglob(pattern, path))
        except Exception as e:
            return GlobResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message=str(e),
            ))

    async def aglob(self, pattern: str, path: VirtualPath = VirtualPath("/workspace")) -> GlobResult:
        norm = self._normalize_path(path)
        result = await self._run_ws_call(
            "glob",
            self._call,
            "glob_files",
            {"pattern": pattern, "path": norm},
        )
        if result is None:
            return GlobResult(error=BackendError(
                code=ErrorCode.IO_ERROR, message="Connection to API client failed",
            ))
        if result.get("error"):
            return GlobResult(error=self._map_error(result, path=path))
        data = result.get("items", [])
        from mambo_agents.backends.protocol import FileInfo

        matches = []
        for item in data:
            matches.append(
                FileInfo(
                    path=VirtualPath(item.get("path", "/")),
                    is_dir=item.get("is_dir", False),
                    size=item.get("size", 0),
                    modified_at=item.get("modified_at", ""),
                )
            )
        return GlobResult(matches=matches)

    # ------------------------------------------------------------------
    # download / upload — raw bytes (bypass text-only read path)
    # ------------------------------------------------------------------

    def download_files(
        self, paths: list[VirtualPath],
    ) -> list[DownloadFileResult]:
        try:
            return self._run_sync(self.adownload_files(paths))
        except Exception as e:
            return [DownloadFileResult(
                path=paths[0] if paths else VirtualPath("/"),
                content=None,
                error=BackendError(code=ErrorCode.IO_ERROR, message=str(e)),
            )]

    async def adownload_files(
        self, paths: list[VirtualPath],
    ) -> list[DownloadFileResult]:
        norms = [self._normalize_path(p) for p in paths]
        result = await self._run_ws_call(
            "download_files",
            self._call,
            "download_files",
            {"paths": norms},
        )
        if result is None:
            return [DownloadFileResult(
                path=p, content=None,
                error=BackendError(code=ErrorCode.IO_ERROR, message="Connection to API client failed"),
            ) for p in paths]

        if isinstance(result, dict) and result.get("error"):
            return [DownloadFileResult(
                path=p, content=None,
                error=self._map_error(result),
            ) for p in paths]

        raw_results: list[dict] = result.get("results", []) if isinstance(result, dict) else []
        out: list[DownloadFileResult] = []
        for i, item in enumerate(raw_results):
            item_path = item.get("path", str(paths[i]) if i < len(paths) else "/")
            if item.get("error"):
                out.append(DownloadFileResult(
                    path=item_path, content=None,
                    error=BackendError(code=ErrorCode.IO_ERROR, message=str(item["error"])),
                ))
            else:
                content_b64 = item.get("content_b64", "")
                content_bytes = base64.b64decode(content_b64) if content_b64 else None
                out.append(DownloadFileResult(path=item_path, content=content_bytes))
        return out

    def upload_files(
        self, files: list[tuple[VirtualPath, bytes]],
    ) -> list[UploadFileResult]:
        try:
            return self._run_sync(self.aupload_files(files))
        except Exception as e:
            return [UploadFileResult(
                path=files[0][0] if files else VirtualPath("/"),
                error=BackendError(code=ErrorCode.IO_ERROR, message=str(e)),
            )]

    async def aupload_files(
        self, files: list[tuple[VirtualPath, bytes]],
    ) -> list[UploadFileResult]:
        payload_files = [
            {"path": self._normalize_path(p), "content_b64": base64.b64encode(data).decode("ascii")}
            for p, data in files
        ]
        result = await self._run_ws_call(
            "upload_files",
            self._call,
            "upload_files",
            {"files": payload_files},
        )
        if result is None:
            return [UploadFileResult(
                path=p, error=BackendError(code=ErrorCode.IO_ERROR, message="Connection to API client failed"),
            ) for p, _ in files]

        if isinstance(result, dict) and result.get("error"):
            return [UploadFileResult(
                path=p, error=self._map_error(result),
            ) for p, _ in files]

        raw_results: list[dict] = result.get("results", []) if isinstance(result, dict) else []
        out: list[UploadFileResult] = []
        for i, item in enumerate(raw_results):
            item_path = item.get("path", str(files[i][0]) if i < len(files) else "/")
            if item.get("error"):
                out.append(UploadFileResult(
                    path=item_path,
                    error=BackendError(code=ErrorCode.IO_ERROR, message=str(item["error"])),
                ))
            else:
                out.append(UploadFileResult(path=item_path))
        return out

    # ------------------------------------------------------------------
    # Extra: execute
    # ------------------------------------------------------------------

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> str:
        """Execute a shell command on the remote client (sync wrapper)."""
        try:
            return self._run_sync(self.aexecute(command, timeout=timeout))
        except Exception as e:
            return f"Error executing command ({type(e).__name__}): {e}"

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> str:
        """Execute a shell command on the remote client via WebSocket.

        Sends an ``execute`` command to the connected API client, which runs
        the shell command locally and returns stdout/stderr.

        Args:
            command: Shell command string to execute.
            timeout: Optional timeout in seconds (overrides default).

        Returns:
            Formatted output string with stdout, stderr, and exit code.
        """
        if not command or not isinstance(command, str):
            return "Error: Command must be a non-empty string."

        effective_timeout = timeout if timeout is not None else self._execute_timeout

        # The WS round-trip timeout must be at least as long as the command's
        # own timeout, otherwise the server aborts waiting (default 60s) while
        # the client is still executing a long command (up to 180s+).
        ws_timeout = max(self.timeout, effective_timeout + 10)

        result = await self._run_ws_call(
            "execute",
            self._call,
            "execute",
            {"command": command, "timeout": effective_timeout},
            timeout=ws_timeout,
        )
        if result is None:
            return "Error: Connection to API client failed."

        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"

        output = result.get("output", "") if isinstance(result, dict) else str(result)
        exit_code = result.get("exit_code", 0) if isinstance(result, dict) else 0
        truncated = result.get("truncated", False) if isinstance(result, dict) else False

        if not output:
            output = "<no output>"

        if truncated:
            output += "\n\n... (output truncated by client)"

        if exit_code != 0:
            output = f"{output.rstrip()}\n\nExit code: {exit_code}"

        return output

    # ------------------------------------------------------------------
    # Extra: tree
    # ------------------------------------------------------------------

    def tree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        try:
            return self._run_sync(self.atree(path, depth))
        except Exception as e:
            return f"Error building tree: {e}"

    async def atree(self, path: VirtualPath = VirtualPath("/workspace"), depth: int = 3) -> str:
        norm = self._normalize_path(path)
        result = await self._run_ws_call(
            "tree",
            self._call,
            "tree",
            {"path": norm, "depth": depth, "ignore_dirs": self.ignore_dirs},
        )
        if result is None:
            return "Error: Connection to API client failed."
        if isinstance(result, dict) and result.get("error"):
            return result["error"]
        return result.get("tree", "") if isinstance(result, dict) else str(result)

    # ------------------------------------------------------------------
    # Extra: delete
    # ------------------------------------------------------------------

    def delete(self, path: VirtualPath) -> DeleteResult:
        try:
            return self._run_sync(self.adelete(path))
        except Exception as e:
            return DeleteResult(
                error=BackendError(code=ErrorCode.IO_ERROR, message=str(e)),
                path=path,
            )

    async def adelete(self, path: VirtualPath) -> DeleteResult:
        try:
            self._check_edit_permission(path)
        except PermissionError as e:
            return DeleteResult(
                error=BackendError(code=ErrorCode.EDIT_NOT_ALLOWED, path=path, message=str(e)),
                path=path,
            )

        norm = self._normalize_path(path)
        result = await self._run_ws_call(
            "delete",
            self._call,
            "delete_file",
            {"path": norm},
        )
        if result is None:
            return DeleteResult(
                error=BackendError(code=ErrorCode.IO_ERROR, message="Connection to API client failed"),
                path=path,
            )
        if result.get("error"):
            return DeleteResult(
                error=self._map_error(result, path=path),
                path=path,
            )
        return DeleteResult(path=path)
