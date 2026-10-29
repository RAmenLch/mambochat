"""生图工具中间件。

把 :class:`ImageGenStandard` 的三个原语包装成 LangChain 工具挂到 Mambo Agent
上。中间件持有 backend，负责把下载到的图片落到 Agent 工作区；协议细节全部
由 standard 实现类承担。
"""

import json
import logging
from typing import Any, Dict, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool
from mambo_agents.backends.protocol import BackendProtocol

from .standard import (
    DEFAULT_WAIT_TIMEOUT,
    IMAGE_TOOL_DOWNLOAD,
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_NAMES,
    IMAGE_TOOL_STATUS,
    ImageDownloadArgs,
    ImageGenStandard,
    ImageGenerateArgs,
    ImageStatusArgs,
)

logger = logging.getLogger(__name__)


_GENERATE_DESCRIPTION = (
    "Generate images from a text prompt using the configured image generation "
    "service. Returns a task id. Use sync=true to wait for completion, or "
    "sync=false and poll with image_task_status for long jobs. "
    "'NumxNum' sets the image resolution as 'WIDTHxHEIGHT' in pixels, e.g. "
    "'1024x1024' or '768x1344'; omit it to use the configured default. "
    "Extra parameters (width/height/steps/seed/model/...) can be passed through "
    "'extra' and are forwarded verbatim to the service."
)

_STATUS_DESCRIPTION = (
    "Check the progress of an image generation task. Returns "
    "{task_id, status, progress, count, error}. status is one of "
    "queued / running / completed / failed / expired; progress may be null "
    "when the backend does not report it. 'wait_timeout' is a number of seconds "
    "to block (default 0 = return immediately); the call returns early as soon as "
    "the task settles, so prefer e.g. wait_timeout=30 instead of tight polling."
)

_DOWNLOAD_DESCRIPTION = (
    "Download the finished images of a task into the agent workspace and return "
    "their file paths. Images are written to disk only — the image data is NOT "
    "returned to you (saves tokens). If the user should see an image, call the "
    "`show` tool with the returned path afterwards. 'path' is REQUIRED: the "
    "target directory as a virtual path under /workspace (e.g. /workspace/images); "
    "a missing or out-of-workspace path is an error. 'prefix' sets the filename "
    "prefix. 'wait_timeout' (seconds, default 0) waits for the task to settle "
    "before downloading."
)


class ImageGenMiddleware(AgentMiddleware):
    """Registers the three image generation tools and owns the backend sink."""

    def __init__(
        self,
        standard: ImageGenStandard,
        backend: Optional[BackendProtocol],
    ) -> None:
        super().__init__()
        self._standard = standard
        self._backend = backend

        self.tools = [
            StructuredTool.from_function(
                name=IMAGE_TOOL_GENERATE,
                description=_GENERATE_DESCRIPTION,
                coroutine=self._agenerate,
                args_schema=ImageGenerateArgs,
                infer_schema=False,
            ),
            StructuredTool.from_function(
                name=IMAGE_TOOL_STATUS,
                description=_STATUS_DESCRIPTION,
                coroutine=self._astatus,
                args_schema=ImageStatusArgs,
                infer_schema=False,
            ),
            StructuredTool.from_function(
                name=IMAGE_TOOL_DOWNLOAD,
                description=_DOWNLOAD_DESCRIPTION,
                coroutine=self._adownload,
                args_schema=ImageDownloadArgs,
                infer_schema=False,
            ),
        ]

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------

    async def _agenerate(
        self,
        prompt: str,
        numxnum: str = "",
        negative_prompt: Optional[str] = None,
        count: int = 1,
        sync: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_GENERATE,
            lambda: self._standard.run_generate(
                ImageGenerateArgs(
                    prompt=prompt,
                    numxnum=numxnum or "",
                    negative_prompt=negative_prompt,
                    count=count,
                    sync=sync,
                    extra=extra,
                )
            ),
        )

    async def _astatus(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_STATUS,
            lambda: self._standard.run_status(
                ImageStatusArgs(task_id=task_id, wait_timeout=wait_timeout)
            ),
        )

    async def _adownload(
        self,
        task_id: str,
        path: str,
        index: Optional[int] = None,
        wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
        prefix: Optional[str] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_DOWNLOAD,
            lambda: self._standard.run_download(
                self._backend,
                ImageDownloadArgs(
                    task_id=task_id,
                    index=index,
                    wait_timeout=wait_timeout,
                    path=path,
                    prefix=prefix,
                ),
            ),
        )

    # ------------------------------------------------------------------
    # 异常安全
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe(tool_name: str, call) -> str:
        """任何异常都转为文本结果，避免生图服务故障中断整个生成流程。"""
        try:
            return await call()
        except Exception as exc:  # noqa: BLE001 - 需要兜底所有后端异常
            logger.warning("image gen tool '%s' failed: %s", tool_name, exc)
            return json.dumps(
                {"is_error": True, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )


def build_image_gen_middleware(
    standard: ImageGenStandard, backend: Optional[BackendProtocol]
) -> ImageGenMiddleware:
    """便捷构造器。"""
    return ImageGenMiddleware(standard=standard, backend=backend)


__all__ = [
    "ImageGenMiddleware",
    "build_image_gen_middleware",
    "IMAGE_TOOL_NAMES",
]
