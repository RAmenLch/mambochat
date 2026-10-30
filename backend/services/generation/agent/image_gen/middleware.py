"""生图工具中间件。

把 :class:`ImageGenStandard` 的三个原语包装成 LangChain 工具挂到 Mambo Agent
上。中间件持有 backend，负责把下载到的图片落到 Agent 工作区；协议细节全部
由 standard 实现类承担。
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool
from mambo_agents.backends.protocol import BackendProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from .standard import (
    DEFAULT_ONESHOT_WAIT_TIMEOUT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RESOLUTION,
    DEFAULT_WAIT_TIMEOUT,
    IMAGE_TOOL_DOWNLOAD,
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_GENERATE_SHOW,
    IMAGE_TOOL_NAMES,
    IMAGE_TOOL_STATUS,
    ImageDownloadArgs,
    ImageGenStandard,
    ImageGenerateArgs,
    ImageGenerateShowArgs,
    ImageStatusArgs,
)

logger = logging.getLogger(__name__)


_GENERATE_DESCRIPTION = (
    "Generate images from a text prompt using the configured image generation "
    "service. Returns a task id. Use sync=true to wait for completion, or "
    "sync=false and poll with image_task_status for long jobs (omit sync to use "
    "the configured default). "
    "'resolution' sets the image resolution as 'WIDTHxHEIGHT' in pixels, e.g. "
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
    "prefix (Chinese / any Unicode text is allowed; only \\ / : * ? \" < > | are "
    "rejected). 'wait_timeout' (seconds, default 0) waits for the task to settle "
    "before downloading."
)

_GENERATE_SHOW_DESCRIPTION = (
    "One-shot image generation AND presentation: generate from a text prompt, "
    "wait for the image, save it into the workspace, and display it to the human "
    "user in one call. Returns {files:[{index, path, file_id, mime}], mode}. "
    "Prefer this tool whenever the user wants to see the generated image. "
    "'resolution' is 'WIDTHxHEIGHT' in pixels (e.g. '1024x1024', '768x1344'); "
    "omit it to use the configured default. 'mode' picks the display mode "
    "(Normal / Mini_Avatar / Gal_Avatar / Group / Spark). 'path' is an optional "
    f"workspace directory for the saved files (default {DEFAULT_OUTPUT_DIR}); if it "
    "ends with a filename like /workspace/images/fox.png the directory and the "
    "filename prefix are inferred from it. 'timeout' is the max seconds to wait "
    f"(default {DEFAULT_ONESHOT_WAIT_TIMEOUT}); if the task is still running by then, "
    "nothing is saved and you get the task_id back so you can continue with "
    "image_task_status / image_download / show. Extra backend parameters "
    "(width/height/steps/seed/model/...) go in 'extra' and are forwarded verbatim."
)

# 两个工具集都开启时，给三件套追加一句指引，避免 LLM 走 4 步
_ONESHOT_HINT = (
    " NOTE: when the user should actually see the image, the one-shot tool "
    "'image_generate_show' does generation + saving + display in a single call — "
    "prefer it over this multi-step flow."
)

# 异步模式下追加的说明：调用立即返回，后续交给平台
_ASYNC_ONESHOT_HINT = (
    " NOTE: this deployment generates images asynchronously — the call returns "
    "immediately with status=pending plus the target file paths, and the platform "
    "saves and displays the images in the background. Do NOT call show or "
    "image_download afterwards; use image_task_status only if you need progress."
)


class ImageGenMiddleware(AgentMiddleware):
    """Registers the image generation tools and owns the backend/file sink.

    Parameters
    ----------
    enable_standard_tools:
        是否注册契约三件套（``image_generate`` / ``image_task_status`` /
        ``image_download``）。
    enable_generate_show:
        是否注册一条龙工具 ``image_generate_show``（生成 + 落盘 + 展示）。
    """

    def __init__(
        self,
        standard: ImageGenStandard,
        backend: Optional[BackendProtocol],
        *,
        session_factory: Optional[Callable[[], AsyncSession]] = None,
        enable_standard_tools: bool = True,
        enable_generate_show: bool = False,
    ) -> None:
        super().__init__()
        self._standard = standard
        self._backend = backend
        self._session_factory = session_factory

        tools = []
        if enable_standard_tools:
            hint = _ONESHOT_HINT if enable_generate_show else ""
            tools.extend(
                [
                    StructuredTool.from_function(
                        name=IMAGE_TOOL_GENERATE,
                        description=_GENERATE_DESCRIPTION + hint,
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
                        description=_DOWNLOAD_DESCRIPTION + hint,
                        coroutine=self._adownload,
                        args_schema=ImageDownloadArgs,
                        infer_schema=False,
                    ),
                ]
            )
        if enable_generate_show:
            description = _GENERATE_SHOW_DESCRIPTION
            if not standard.default_sync:
                description += _ASYNC_ONESHOT_HINT
            tools.append(
                StructuredTool.from_function(
                    name=IMAGE_TOOL_GENERATE_SHOW,
                    description=description,
                    coroutine=self._agenerate_show,
                    args_schema=ImageGenerateShowArgs,
                    infer_schema=False,
                )
            )
        self.tools = tools

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------

    async def _agenerate(
        self,
        prompt: str,
        resolution: str = DEFAULT_RESOLUTION,
        negative_prompt: Optional[str] = None,
        count: int = 1,
        sync: Optional[bool] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_GENERATE,
            lambda: self._standard.run_generate(
                ImageGenerateArgs(
                    prompt=prompt,
                    resolution=resolution or "",
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

    async def _agenerate_show(
        self,
        prompt: str,
        resolution: str = DEFAULT_RESOLUTION,
        negative_prompt: Optional[str] = None,
        count: int = 1,
        extra: Optional[Dict[str, Any]] = None,
        mode: str = "Normal",
        path: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_GENERATE_SHOW,
            lambda: self._standard.run_generate_show(
                self._backend,
                self._session_factory,
                ImageGenerateShowArgs(
                    prompt=prompt,
                    resolution=resolution or "",
                    negative_prompt=negative_prompt,
                    count=count,
                    extra=extra,
                    mode=mode,
                    path=path,
                    timeout=timeout,
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
    standard: ImageGenStandard,
    backend: Optional[BackendProtocol],
    *,
    session_factory: Optional[Callable[[], AsyncSession]] = None,
    enable_standard_tools: bool = True,
    enable_generate_show: bool = False,
) -> ImageGenMiddleware:
    """便捷构造器。"""
    return ImageGenMiddleware(
        standard=standard,
        backend=backend,
        session_factory=session_factory,
        enable_standard_tools=enable_standard_tools,
        enable_generate_show=enable_generate_show,
    )


__all__ = [
    "ImageGenMiddleware",
    "build_image_gen_middleware",
    "IMAGE_TOOL_NAMES",
]
