# backend/services/generation/agent/mambo_api_backend.py

"""API Backend for Mambo Agents.

Provides filesystem access via a WebSocket-connected client, implementing
``mambo_agents.backends.protocol.BackendProtocol``.

The client actively connects to the MamboChat server's WebSocket endpoint.
This backend sends file operation commands through the WebSocket and waits
for the client to execute them and return results.

Unlike the deepagents version, this returns mambo_agents-style result types
(LsResult, ReadResult, WriteResult, etc.) instead of deepagents-style types.
"""

import base64
import fnmatch
import logging
import posixpath
from typing import Any

from langchain_core.tools import StructuredTool

from mambo_agents.backends.protocol import (
    BackendProtocol,
    EditResult,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

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
        timeout: float = 60.0,
    ) -> None:
        super().__init__()
        self.backend_id = backend_id
        self.backend_name = backend_name or backend_id
        self.edit_whitelist = edit_whitelist or []
        self.edit_blacklist = edit_blacklist or []
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return f"api://{self.backend_name}"

    @property
    def tools(self) -> list[StructuredTool]:
        """Extra tools — API backend has no built-in extras beyond core six."""
        return []

    @property
    def description(self) -> str:
        return (
            f"API-connected remote filesystem '{self.backend_name}'. "
            "Works with files on a remote client machine. "
            "The read tool defaults to no line numbers. "
            "Set include_line_numbers=True when you need to reference specific lines."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    async def _call(self, method: str, params: dict) -> dict:
        """Send a command to the client via WebSocket and wait for response."""
        offline_msg = self._check_online()
        if offline_msg:
            raise ConnectionError(offline_msg)

        from backend.routers.api_client_router import send_command

        return await send_command(
            self.backend_id, method, params, timeout=self.timeout
        )

    def _normalize_path(self, virtual_path: str) -> str:
        """Normalize a virtual path: ensure leading /, prevent traversal."""
        if not virtual_path.startswith("/"):
            virtual_path = "/" + virtual_path
        norm = posixpath.normpath(virtual_path)
        if norm.startswith(".."):
            raise ValueError("Path traversal not allowed.")
        return norm

    def _check_edit_permission(self, virtual_path: str) -> None:
        filename = posixpath.basename(virtual_path)
        if self.edit_whitelist and not any(
            fnmatch.fnmatch(filename, p) for p in self.edit_whitelist
        ):
            raise PermissionError(
                f"Edit denied: File '{filename}' is not in the edit whitelist."
            )
        if self.edit_blacklist and any(
            fnmatch.fnmatch(filename, p) for p in self.edit_blacklist
        ):
            raise PermissionError(
                f"Edit denied: File '{filename}' is in the edit blacklist."
            )

    async def _run_ws_call(
        self,
        operation: str,
        fn,
        *args,
        **kwargs,
    ):
        """Shared pattern: run fn(...), catch ConnectionError/TimeoutError."""
        try:
            return fn(*args, **kwargs)
        except (ConnectionError, TimeoutError) as e:
            logger.error("API Backend %s failed: %s", operation, e)
            return None

    # ------------------------------------------------------------------
    # Core file operations (mambo BackendProtocol)
    # ------------------------------------------------------------------

    def _ls_sync(self, path: str) -> LsResult:
        """Sync ls via event-loop delegation."""
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return LsResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(asyncio.run, self.als(path)).result()
            except Exception as e:
                return LsResult(error=str(e))

    def ls(self, path: str) -> LsResult:
        return self._ls_sync(path)

    async def als(self, path: str) -> LsResult:
        norm = self._normalize_path(path)
        result = await self._run_ws_call("ls", self._call, "ls", {"path": norm})
        if result is None:
            return LsResult(error="Connection to API client failed")

        data = result if isinstance(result, list) else result.get("items", [])
        entries = []
        from mambo_agents.backends.protocol import FileInfo

        for item in data:
            entries.append(
                FileInfo(
                    path=item.get("path", ""),
                    is_dir=item.get("is_dir", False),
                    size=item.get("size", 0),
                    modified_at=item.get("modified_at", ""),
                )
            )
        return LsResult(entries=entries)

    def _read_sync(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return ReadResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(
                    asyncio.run,
                    self.aread_raw(file_path, offset, limit, include_line_numbers),
                ).result()
            except Exception as e:
                return ReadResult(error=str(e))

    def read_raw(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        return self._read_sync(file_path, offset, limit, include_line_numbers)

    async def aread_raw(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = False,
    ) -> ReadResult:
        norm = self._normalize_path(file_path)
        result = await self._run_ws_call(
            "read", self._call, "read_file", {"path": norm, "offset": offset, "limit": limit}
        )
        if result is None:
            return ReadResult(error=f"Connection to API client failed")

        if result.get("error"):
            return ReadResult(error=f"Error reading file '{file_path}': {result['error']}")

        content = result.get("content", "")
        lines = result.get("lines")
        if lines is not None:
            content = self._format_with_line_numbers(lines, start=offset + 1)

        total = content.count("\n") + 1 if content else 0
        return ReadResult(content=content, total_lines=total, encoding="utf-8")

    @staticmethod
    def _format_with_line_numbers(
        lines: list[str], start: int = 1
    ) -> str:
        width = max(3, len(str(start + len(lines) - 1)))
        result = []
        for i, line in enumerate(lines):
            result.append(f"{start + i:>{width}}  {line}")
        return "\n".join(result)

    def write(
        self, file_path: str, content: str, overwrite: bool = False
    ) -> WriteResult:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return WriteResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(
                    asyncio.run, self.awrite(file_path, content, overwrite)
                ).result()
            except Exception as e:
                return WriteResult(error=str(e))

    async def awrite(
        self, file_path: str, content: str, overwrite: bool = False
    ) -> WriteResult:
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return WriteResult(error=str(e))

        norm = self._normalize_path(file_path)
        result = await self._run_ws_call(
            "write",
            self._call,
            "write_file",
            {"path": norm, "content": content},
        )
        if result is None:
            return WriteResult(error="Connection to API client failed")
        if result.get("error"):
            return WriteResult(error=result["error"])
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return EditResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(
                    asyncio.run,
                    self.aedit(file_path, old_str, new_str, replace_all=replace_all),
                ).result()
            except Exception as e:
                return EditResult(error=str(e))

    async def aedit(
        self,
        file_path: str,
        old_str: str,
        new_str: str,
        *,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return EditResult(error=str(e))

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
            return EditResult(error="Connection to API client failed")
        if result.get("error"):
            return EditResult(error=result["error"])
        return EditResult(
            path=file_path,
            occurrences=result.get("occurrences", 0),
        )

    def grep(
        self, pattern: str, path: str = "/", glob: str | None = None,
        regex: bool = False,
    ) -> GrepResult:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return GrepResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(
                    asyncio.run, self.agrep(pattern, path, glob, regex)
                ).result()
            except Exception as e:
                return GrepResult(error=str(e))

    async def agrep(
        self, pattern: str, path: str = "/", glob: str | None = None,
        regex: bool = False,
    ) -> GrepResult:
        search_path = self._normalize_path(path) if path else "/"
        result = await self._run_ws_call(
            "grep",
            self._call,
            "grep_files",
            {"pattern": pattern, "path": search_path, "glob": glob, "regex": regex},
        )
        if result is None:
            return GrepResult(error="Connection to API client failed")
        if isinstance(result, dict) and result.get("error"):
            return GrepResult(error=result["error"])
        if isinstance(result, list):
            matches: list[GrepMatch] = []
            for m in result:
                matches.append(
                    GrepMatch(
                        path=m.get("path", ""),
                        line=m.get("line", 0),
                        text=m.get("text", ""),
                    )
                )
            return GrepResult(matches=matches)
        return GrepResult(matches=[])

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return GlobResult(error="No event loop available")

        with concurrent.futures.ThreadPoolExecutor() as pool:
            try:
                return pool.submit(
                    asyncio.run, self.aglob(pattern, path)
                ).result()
            except Exception as e:
                return GlobResult(error=str(e))

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        norm = self._normalize_path(path)
        result = await self._run_ws_call(
            "glob",
            self._call,
            "glob_files",
            {"pattern": pattern, "path": norm},
        )
        if result is None:
            return GlobResult(error="Connection to API client failed")
        data = result if isinstance(result, list) else result.get("items", [])
        from mambo_agents.backends.protocol import FileInfo

        matches = []
        for item in data:
            matches.append(
                FileInfo(
                    path=item.get("path", ""),
                    is_dir=item.get("is_dir", False),
                    size=item.get("size", 0),
                    modified_at=item.get("modified_at", ""),
                )
            )
        return GlobResult(matches=matches)
