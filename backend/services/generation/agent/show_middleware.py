"""Show tool middleware for Mambo Agent.

Intercepts ``show`` tool calls, reads the target file from the backend,
persists it via ``FileService``, and returns structured metadata in the
``ToolMessage``.  The UI layer (``MamboAgentBuiltinToolProvider``) picks
up the result and emits a ``FILE`` sub-message for frontend display.
"""

import json
from pathlib import PurePosixPath
from typing import Callable

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import BaseModel, Field

from mambo_agents.backends.protocol import BackendProtocol, _get_mime_type
from mambo_agents.backends.schemas import VirtualPath
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.enums import FileManagementType
from backend.services.file_service import FileService


class ShowInput(BaseModel):
    """Args schema for the ``show`` tool."""

    path: str = Field(description="文件虚拟路径，例如 /workspace/image.png")


_SHOW_TOOL_DESCRIPTION = (
    "Display a file (text or image) to the **human user** in the chat UI. "
    "After calling this tool, the file appears as a card or inline image below "
    "your message — visible to the User only, NOT to you. "
    "IMPORTANT: You will NOT receive the file content in the tool result — "
    "you only get back a file_id / filename / mime_type metadata blob. "
    "Therefore, after calling show, do NOT describe or analyse the file "
    "contents unless you already knew them from a prior read. "
    "To know what a text file contains, use read first. "
    "Images cannot be read at all — only the User can see them after show."
)


async def _download_safe(
    backend: BackendProtocol, path: str,
) -> tuple[bytes | None, str | None]:
    """Download file bytes from backend; return (content_bytes, error_str).

    Uses ``adownload_files`` (async protocol method) so that backends with
    per-instance locks (e.g. ``SshBackend._async_lock``) can serialize
    SFTP access and avoid paramiko deadlocks on concurrent calls.
    """
    try:
        results = await backend.adownload_files([VirtualPath(path)])
        if not results:
            return None, "adownload_files returned empty results"
        r = results[0]
        if r.error:
            return None, r.error
        return r.content, None
    except Exception as exc:
        return None, str(exc)


class ShowMiddleware(AgentMiddleware):
    """Middleware that intercepts ``show`` tool calls.

    Reads the file from the current backend, persists it to the file store,
    and returns a JSON blob with the ``file_id`` so that the
    ``MamboAgentBuiltinToolProvider`` can create a ``FILE`` sub-message.

    Parameters
    ----------
    backend:
        The backend providing file-system operations (reads the file).
    session_factory:
        Async callable returning a fresh ``AsyncSession`` for
        ``FileService``.
    """

    def __init__(
        self,
        backend: BackendProtocol,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        super().__init__()
        self._backend = backend
        self._session_factory = session_factory

        self.tools = [
            StructuredTool.from_function(
                name="show",
                description=_SHOW_TOOL_DESCRIPTION,
                coroutine=self._ashow,
                args_schema=ShowInput,
                infer_schema=False,
            )
        ]

    # ------------------------------------------------------------------
    # Tool implementation
    # ------------------------------------------------------------------

    async def _ashow(self, path: str) -> str:
        """Core logic: download → persist → return metadata."""
        content_bytes, error = await _download_safe(self._backend, path)
        if error:
            return json.dumps({"error": error})

        filename = PurePosixPath(path).name
        mime = _get_mime_type(path)

        # If the content is valid UTF-8 text, treat it as text regardless of
        # file extension.  This handles files like .env, Dockerfile, or other
        # non-.txt extensions that contain plain UTF-8 text but whose MIME
        # type was guessed as application/octet-stream (or another non-text
        # type) by mimetypes / _get_mime_type.
        if content_bytes:
            sample = content_bytes[:8192]
            try:
                sample.decode("utf-8")
                # Content is valid UTF-8 → use FileUtils to resolve the proper
                # text MIME type (falling back to text/plain when the extension
                # is not in the map).
                from backend.utils.file_utils import FileUtils
                mime = FileUtils.correct_mime_type(filename, mime, sample)
            except (UnicodeDecodeError, ValueError, LookupError):
                # Not valid UTF-8 text; keep the original MIME guess and let
                # save_file_from_bytes perform its own detection / rejection.
                pass

        async with self._session_factory() as db:
            fs = FileService(db)
            db_file = await fs.save_file_from_bytes(
                data=content_bytes or b"",
                filename=filename,
                mime_type=mime,
                management_type=[FileManagementType.SUB_MESSAGE.value],
                sub_path="chat_attachments",
            )

        return json.dumps({
            "file_id": db_file.id,
            "filename": filename,
            "mime_type": mime,
        })

    # ------------------------------------------------------------------
    # Middleware hooks (delegate to default — no wrapping needed)
    # ------------------------------------------------------------------

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable,
    ) -> ToolMessage:
        """Delegate to the default tool executor; all logic lives in ``_ashow``."""
        return await handler(request)
