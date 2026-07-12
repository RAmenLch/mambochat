# backend/services/generation/agent/api_backend.py

"""API Backend for DeepAgents.

Provides filesystem access via a WebSocket-connected client.
The client actively connects to the MamboChat server's WebSocket endpoint.
This backend sends file operation commands through the WebSocket and waits
for the client to execute them and return results.

The server does NOT need to know the client's physical root directory.
Virtual paths (e.g. /src/main.py) are passed directly to the client,
which resolves them relative to its own --root-dir.
"""

import asyncio
import base64
import logging
import posixpath
import fnmatch
from typing import Any

from deepagents.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    SandboxBackendProtocol,
    WriteResult,
)
from deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
)

from backend.services.generation.agent.tree_extension import TreeBackendProtocol

logger = logging.getLogger(__name__)


class APIBackend(SandboxBackendProtocol, TreeBackendProtocol):
    """Backend that proxies file operations to a WebSocket-connected client.

    The client connects to the server's WebSocket endpoint at:
      ws://server/api/api-client/ws/{backend_id}?api_key=xxx

    All file operations are sent as JSON commands through the WebSocket,
    and results are returned by the client.

    The server passes virtual paths directly to the client. The client
    resolves them relative to its own root directory.

    Also supports shell command execution via the client's subprocess.
    """

    def __init__(
        self,
        backend_id: str,
        backend_name: str = "",
        edit_whitelist: list[str] | None = None,
        edit_blacklist: list[str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.backend_id = backend_id
        self.backend_name = backend_name or backend_id
        self.edit_whitelist = edit_whitelist or []
        self.edit_blacklist = edit_blacklist or []
        self.timeout = timeout

    @property
    def id(self) -> str:
        """Unique identifier for the sandbox backend instance."""
        return f"api://{self.backend_name}"

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Sync execute — delegates to aexecute via asyncio.

        Since this backend communicates over WebSocket (async), the sync
        version schedules the async call on the running event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.aexecute(command, timeout=timeout)).result()
        except RuntimeError:
            pass

        try:
            main_loop = asyncio.get_event_loop()
        except RuntimeError:
            main_loop = None

        if main_loop and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.aexecute(command, timeout=timeout), main_loop
            )
            try:
                return future.result(timeout=(timeout or 120) + 5)
            except Exception as e:
                return ExecuteResponse(output=f"Error executing command: {e}", exit_code=1)

        return asyncio.run(self.aexecute(command, timeout=timeout))

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command on the API client's machine via WebSocket."""
        try:
            result = await self._call("execute", {
                "command": command,
                "timeout": timeout,
            })
        except (ConnectionError, TimeoutError) as e:
            return ExecuteResponse(output=f"Error executing command: {e}", exit_code=1)

        if result.get("error"):
            return ExecuteResponse(output=result["error"], exit_code=1)

        return ExecuteResponse(
            output=result.get("output", ""),
            exit_code=result.get("exit_code"),
            truncated=result.get("truncated", False),
        )

    def _check_online(self) -> str | None:
        """Check if the API client is currently connected.

        Returns None if online, otherwise returns an error message string.
        """
        from backend.routers.api_client_router import get_client_connection
        if get_client_connection(self.backend_id) is None:
            return (
                f"Backend \"{self.backend_name}\" 当前不在线。"
                f"请确认 API 客户端已启动并成功连接到服务器后再试。"
            )
        return None

    async def _call(self, method: str, params: dict) -> dict:
        """Send a command to the client via WebSocket and wait for response."""
        # Pre-flight online check
        offline_msg = self._check_online()
        if offline_msg:
            raise ConnectionError(offline_msg)
        from backend.routers.api_client_router import send_command
        return await send_command(self.backend_id, method, params, timeout=self.timeout)

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
        if self.edit_whitelist and not any(fnmatch.fnmatch(filename, p) for p in self.edit_whitelist):
            raise PermissionError(f"Edit denied: File '{filename}' is not in the edit whitelist.")
        if self.edit_blacklist and any(fnmatch.fnmatch(filename, p) for p in self.edit_blacklist):
            raise PermissionError(f"Edit denied: File '{filename}' is in the edit blacklist.")

    async def als_info(self, path: str) -> list[FileInfo]:
        norm = self._normalize_path(path)
        try:
            result = await self._call("ls", {"path": norm})
        except (ConnectionError, TimeoutError) as e:
            logger.error("API Backend ls failed: %s", e)
            return []
        data = result.get("items", [])
        items: list[FileInfo] = []
        for item in data:
            items.append({
                "path": item.get("path", ""),
                "is_dir": item.get("is_dir", False),
                "size": item.get("size", 0),
                "modified_at": item.get("modified_at", ""),
            })
        items.sort(key=lambda x: x.get("path", ""))
        return items

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        norm = self._normalize_path(file_path)
        try:
            result = await self._call("read_file", {
                "path": norm, "offset": offset, "limit": limit
            })
        except (ConnectionError, TimeoutError) as e:
            return f"Error reading file '{file_path}': {e}"

        if result.get("error"):
            return f"Error reading file '{file_path}': {result['error']}"

        content = result.get("content", "")
        lines_key = "lines" if "lines" in result else None

        if lines_key is not None:
            lines = result[lines_key]
            return format_content_with_line_numbers(lines, start_line=offset + 1)

        empty_msg = check_empty_content(content)
        if empty_msg:
            return empty_msg

        return content

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return WriteResult(error=str(e))

        norm = self._normalize_path(file_path)
        try:
            result = await self._call("write_file", {
                "path": norm, "content": content
            })
        except (ConnectionError, TimeoutError) as e:
            return WriteResult(error=str(e))

        if result.get("error"):
            return WriteResult(error=result["error"])
        return WriteResult(path=file_path, files_update=None)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        try:
            self._check_edit_permission(file_path)
        except PermissionError as e:
            return EditResult(error=str(e))

        norm = self._normalize_path(file_path)
        try:
            result = await self._call("edit_file", {
                "path": norm,
                "old_string": old_string,
                "new_string": new_string,
                "replace_all": replace_all,
            })
        except (ConnectionError, TimeoutError) as e:
            return EditResult(error=str(e))

        if result.get("error"):
            return EditResult(error=result["error"])
        return EditResult(
            path=file_path,
            files_update=None,
            occurrences=result.get("occurrences", 0),
        )

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        norm = self._normalize_path(path)
        try:
            result = await self._call("glob_files", {
                "pattern": pattern, "path": norm
            })
        except (ConnectionError, TimeoutError):
            return []
        data = result.get("items", [])
        items: list[FileInfo] = []
        for item in data:
            items.append({
                "path": item.get("path", ""),
                "is_dir": item.get("is_dir", False),
                "size": item.get("size", 0),
                "modified_at": item.get("modified_at", ""),
            })
        items.sort(key=lambda x: x.get("path", ""))
        return items

    async def agrep_raw(self, pattern: str, path: str | None = None, glob: str | None = None,
                        regex: bool = True, offset: int = 0, limit: int | None = None) -> list[GrepMatch] | str:
        search_path = self._normalize_path(path) if path else "/"
        try:
            result = await self._call("grep_files", {
                "pattern": pattern,
                "path": search_path,
                "glob": glob,
                "regex": regex,
                "offset": offset,
                "limit": limit,
            })
        except (ConnectionError, TimeoutError) as e:
            return f"Error: {e}"

        if isinstance(result, dict) and result.get("error"):
            return f"Error: {result['error']}"
        data = result.get("matches", [])
        matches: list[GrepMatch] = []
        for m in data:
            matches.append({
                "path": m.get("path", ""),
                "line": m.get("line", 0),
                "text": m.get("text", ""),
            })
        return matches

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        file_items = []
        for vpath, content in files:
            file_items.append({
                "path": self._normalize_path(vpath),
                "content_b64": base64.b64encode(content).decode('ascii'),
            })
        try:
            result = await self._call("upload_files", {"files": file_items})
        except (ConnectionError, TimeoutError) as e:
            for vpath, _ in files:
                responses.append(FileUploadResponse(path=vpath, error=str(e)))
            return responses

        data = result.get("results", [])
        for item in data:
            responses.append(FileUploadResponse(
                path=item.get("path", ""),
                error=item.get("error"),
            ))
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        normalized = [self._normalize_path(p) for p in paths]
        try:
            result = await self._call("download_files", {"paths": normalized})
        except (ConnectionError, TimeoutError) as e:
            return [FileDownloadResponse(path=p, error=str(e)) for p in paths]

        data = result.get("results", [])
        responses: list[FileDownloadResponse] = []
        for item in data:
            content = None
            if item.get("content_b64"):
                try:
                    content = base64.b64decode(item["content_b64"])
                except Exception:
                    pass
            responses.append(FileDownloadResponse(
                path=item.get("path", ""),
                content=content,
                error=item.get("error"),
            ))
        return responses

    def tree(self, path: str = "/", depth: int = 3) -> str:
        """Sync tree method - delegates to atree."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.atree(path, depth)).result()
        except RuntimeError:
            pass  # no running loop in this thread

        # When called from a thread-pool (e.g. asyncio.to_thread), creating a
        # new event loop with asyncio.run() breaks WebSocket communication on
        # Windows: the response future is resolved on the main loop but the
        # new loop's selector is never woken up (ProactorEventLoop limitation).
        # Instead, schedule the coroutine on the main event loop.
        try:
            main_loop = asyncio.get_event_loop()
        except RuntimeError:
            main_loop = None

        if main_loop and main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.atree(path, depth), main_loop
            )
            try:
                return future.result(timeout=self.timeout + 5)
            except Exception as e:
                return f"Error building tree for {path}: {e}"

        # Last resort — no usable loop at all
        return asyncio.run(self.atree(path, depth))

    async def atree(self, path: str = "/", depth: int = 3) -> str:
        norm = self._normalize_path(path)
        try:
            result = await self._call("tree", {
                "path": norm, "depth": depth
            })
        except (ConnectionError, TimeoutError) as e:
            return f"Error building tree for {path}: {e}"

        tree_str = result.get("tree", "")
        if not tree_str:
            return f"No files found in {path}"
        lines = tree_str.splitlines()
        if lines:
            lines[0] = path
        return "\n".join(lines)
