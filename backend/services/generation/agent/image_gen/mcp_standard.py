"""生图标准框架的 MCP 实现。

通过 MCP 协议与符合标准的生图服务通信：三个原语分别对应三个固定工具名，
``download`` 只接受携带图片数据的 ``ImageContent``（拒绝只给 URL 的
``ResourceLink``），由平台负责落盘。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from mambo_agents.middleware.mcp import MCPServerConfig
from mcp.types import CallToolResult, ImageContent, TextContent

from .standard import (
    DEFAULT_WAIT_TIMEOUT,
    IMAGE_TOOL_DOWNLOAD,
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_STATUS,
    RESOLUTION_ARG,
    ImageBlob,
    ImageGenStandard,
    ImageGenToolError,
)

logger = logging.getLogger(__name__)


class McpImageGenStandard(ImageGenStandard):
    """基于 MCP 协议的生图标准实现。

    Parameters
    ----------
    server_config:
        已解析好的 MCP 服务配置（含 proxy / timeout / env 等），
        由 initializer 依据 ``ImageGenConfig.mcpServerId`` 组装。
    """

    def __init__(
        self,
        server_config: MCPServerConfig,
        *,
        default_count: int = 1,
        default_sync: bool = True,
        default_resolution: str = "",
        default_wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
    ) -> None:
        super().__init__(
            default_count=default_count,
            default_sync=default_sync,
            default_resolution=default_resolution,
            default_wait_timeout=default_wait_timeout,
        )

        self._server_config = server_config
        self._client = MultiServerMCPClient(
            {server_config.name: server_config.to_connection()}
        )

    @property
    def server_name(self) -> str:
        return self._server_config.name

    # ------------------------------------------------------------------
    # 协议调用
    # ------------------------------------------------------------------

    async def _call(self, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        try:
            async with self._client.session(self._server_config.name) as session:
                result = await session.call_tool(tool_name, arguments)
        except ImageGenToolError:
            raise
        except Exception as exc:
            raise ImageGenToolError(
                f"调用生图服务工具 {tool_name} 失败: {type(exc).__name__}: {exc}"
            ) from exc

        if getattr(result, "isError", False):
            raise ImageGenToolError(self._error_text(result, tool_name))
        return result

    @staticmethod
    def _error_text(result: CallToolResult, tool_name: str) -> str:
        parts = [
            block.text
            for block in result.content or []
            if isinstance(block, TextContent) and block.text
        ]
        detail = "\n".join(parts).strip() or "服务未给出错误详情"
        return f"生图服务工具 {tool_name} 返回错误: {detail}"

    @staticmethod
    def _extract_payload(result: CallToolResult) -> Dict[str, Any]:
        """优先取 structuredContent，其次解析文本中的 JSON。"""
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return McpImageGenStandard._unwrap(dict(structured))

        texts = [
            block.text
            for block in result.content or []
            if isinstance(block, TextContent) and block.text
        ]
        joined = "\n".join(texts).strip()
        if not joined:
            raise ImageGenToolError("生图服务返回了空内容")

        try:
            parsed = json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return {"raw": joined}

        if isinstance(parsed, dict):
            return McpImageGenStandard._unwrap(parsed)
        return {"value": parsed}

    @staticmethod
    def _unwrap(payload: Dict[str, Any]) -> Dict[str, Any]:
        """兼容 FastMCP 把返回值包成 ``{"result": {...}}`` 的行为。"""
        if len(payload) == 1 and isinstance(payload.get("result"), dict):
            return dict(payload["result"])
        return payload

    # ------------------------------------------------------------------
    # 原语实现
    # ------------------------------------------------------------------

    async def submit(
        self,
        prompt: str,
        negative_prompt: Optional[str],
        count: int,
        sync: bool,
        extra: Dict[str, Any],
        resolution: Optional[str] = None,
    ) -> Dict[str, Any]:
        arguments: Dict[str, Any] = {
            "prompt": prompt,
            "count": count,
            "sync": sync,
        }
        if negative_prompt:
            arguments["negative_prompt"] = negative_prompt
        if resolution:
            arguments[RESOLUTION_ARG] = resolution
        arguments.update(extra or {})

        result = await self._call(IMAGE_TOOL_GENERATE, arguments)
        return self._extract_payload(result)

    async def status(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> Dict[str, Any]:
        # wait_timeout 必须显式下发（含 0）：缺省时服务端会按自己的默认值
        # 长时间阻塞，导致平台侧的轮询节流与超时判定失效。
        timeout = self._clamp_wait_timeout(wait_timeout)
        arguments: Dict[str, Any] = {"task_id": task_id, "wait_timeout": timeout}
        result = await self._call(IMAGE_TOOL_STATUS, arguments)
        return self._extract_payload(result)

    async def download(
        self, task_id: str, index: Optional[int] = None
    ) -> List[ImageBlob]:
        arguments: Dict[str, Any] = {"task_id": task_id}
        if index is not None:
            arguments["index"] = int(index)

        result = await self._call(IMAGE_TOOL_DOWNLOAD, arguments)

        blobs: List[ImageBlob] = []
        for block in result.content or []:
            if isinstance(block, ImageContent):
                mime = (block.mimeType or "").strip().lower()
                if not mime.startswith("image/"):
                    raise ImageGenToolError(
                        f"生图服务返回的图片 mimeType 不合规: {block.mimeType!r}"
                    )
                if not block.data:
                    raise ImageGenToolError("生图服务返回的图片数据为空")
                blobs.append(
                    ImageBlob(index=len(blobs), mime_type=mime, base64_data=block.data)
                )
            elif getattr(block, "type", None) in ("resource_link", "resource"):
                raise ImageGenToolError(
                    "生图服务返回了资源链接而非图片数据；标准要求 download "
                    "直接返回 ImageContent(base64)"
                )

        if not blobs:
            raise ImageGenToolError(
                f"任务 {task_id} 未返回任何图片数据（可能尚未完成或该 index 无产出）"
            )

        if index is not None:
            for blob in blobs:
                blob.index = int(index)
        return blobs
