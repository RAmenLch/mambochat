"""生图工具中间件。

把 :class:`ImageGenStandard` 的三个原语包装成 LangChain 工具挂到 Mambo Agent
上。中间件持有 backend，负责把下载到的图片落到 Agent 工作区；协议细节全部
由 standard 实现类承担。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool
from mambo_agents.backends.protocol import BackendProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from .registry import ImageGenEntry, build_generator_catalog, pick_generator
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
    MAX_REFERENCE_BYTES,
    MAX_REFERENCE_IMAGES,
    MAX_REFERENCE_TOTAL_BYTES,
    ImageDownloadArgs,
    ImageStatusArgs,
    generate_args_model,
    generate_show_args_model,
)

logger = logging.getLogger(__name__)

# 任务归属表上限：超过即整体清空（单次运行的任务数远小于此值）
_MAX_TRACKED_TASKS = 256


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

# 支持参考图时追加的参数说明（不支持时该参数根本不进 schema）
_REFERENCE_HINT = (
    " 'reference_images' (optional) is a list of workspace virtual paths under "
    "/workspace pointing at existing image files (uploaded user images live under "
    "/.mambo/chat_user_file/, previously generated images under /workspace/images/). "
    "The platform reads them and sends the image data to the backend to guide "
    "generation (image-to-image / style or character reference). "
    f"At most {MAX_REFERENCE_IMAGES} images, each ≤ "
    f"{MAX_REFERENCE_BYTES // (1024 * 1024)}MB and ≤ "
    f"{MAX_REFERENCE_TOTAL_BYTES // (1024 * 1024)}MB in total; png / jpeg / webp / "
    "gif / bmp only. A missing file, unsupported format or exceeded limit is an error."
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
    "target directory as a virtual path under /workspace and it MUST end with '/' "
    "(e.g. /workspace/images/); a missing, non-directory or out-of-workspace path "
    "is an error. 'prefix' sets the filename "
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
    f"workspace path for the saved files (default {DEFAULT_OUTPUT_DIR}); a path "
    "ending with '/' is a directory, otherwise the last segment is a filename and "
    "the directory + filename prefix are inferred from it (e.g. "
    "/workspace/images/fox.png). 'timeout' is the max seconds to wait "
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


class ImageGenMiddleware(AgentMiddleware):
    """Registers the image generation tools and owns the backend/file sink.

    Parameters
    ----------
    entries:
        该 Agent 挂载的生图配置（顺序 = 前端配置顺序，第一个为该工具的默认）。
        每次工具调用按 LLM 传入的 ``image_generator`` 名称选择其一。
    enable_standard_tools:
        是否注册契约三件套（``image_generate`` / ``image_task_status`` /
        ``image_download``）。
    enable_generate_show:
        是否注册一条龙工具 ``image_generate_show``（生成 + 落盘 + 展示）。
    """

    def __init__(
        self,
        entries: List[ImageGenEntry],
        backend: Optional[BackendProtocol],
        *,
        session_factory: Optional[Callable[[], AsyncSession]] = None,
        enable_standard_tools: bool = True,
        enable_generate_show: bool = False,
    ) -> None:
        super().__init__()
        self._entries = [entry for entry in entries if entry.standard is not None]
        self._backend = backend
        self._session_factory = session_factory
        # task_id → 创建它的配置名：状态/下载工具没有 image_generator 参数，
        # 靠这张表在同一次运行内还原「这个任务是谁提交的」。
        self._task_owner: Dict[str, str] = {}

        # 任一配置支持参考图就暴露该参数；选中不支持的配置由标准实现报错说明
        self._with_reference = any(
            entry.standard.supports_reference_images for entry in self._entries
        )
        ref_hint = _REFERENCE_HINT if self._with_reference else ""
        self._generate_args_cls = generate_args_model(self._with_reference)
        self._generate_show_args_cls = generate_show_args_model(self._with_reference)

        tools = []
        if enable_standard_tools:
            hint = _ONESHOT_HINT if enable_generate_show else ""
            # 可用配置清单（名称 + 说明 + 该配置的额外参数）按配置快照确定性渲染
            catalog = build_generator_catalog(self._entries, IMAGE_TOOL_GENERATE)
            tools.extend(
                [
                    StructuredTool.from_function(
                        name=IMAGE_TOOL_GENERATE,
                        description=_GENERATE_DESCRIPTION + ref_hint + hint + catalog,
                        coroutine=self._agenerate,
                        args_schema=self._generate_args_cls,
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
            description = (
                _GENERATE_SHOW_DESCRIPTION
                + ref_hint
                + build_generator_catalog(self._entries, IMAGE_TOOL_GENERATE_SHOW)
            )
            tools.append(
                StructuredTool.from_function(
                    name=IMAGE_TOOL_GENERATE_SHOW,
                    description=description,
                    coroutine=self._agenerate_show,
                    args_schema=self._generate_show_args_cls,
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
        reference_images: Optional[List[str]] = None,
        image_generator: Optional[str] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_GENERATE,
            lambda: self._do_generate(
                image_generator=image_generator,
                prompt=prompt,
                resolution=resolution,
                negative_prompt=negative_prompt,
                count=count,
                sync=sync,
                extra=extra,
                reference_images=reference_images,
            ),
        )

    async def _do_generate(
        self, *, image_generator: Optional[str] = None, **fields: Any
    ) -> str:
        entry = pick_generator(self._entries, image_generator, IMAGE_TOOL_GENERATE)
        raw = await entry.standard.run_generate(
            self._backend,
            self._generate_args_cls(**self._generate_args(**fields)),
        )
        self._remember_task(raw, entry)
        return raw

    async def _astatus(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_STATUS,
            lambda: self._entry_for_task(task_id).standard.run_status(
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
            lambda: self._entry_for_task(task_id).standard.run_download(
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
        reference_images: Optional[List[str]] = None,
        image_generator: Optional[str] = None,
    ) -> str:
        return await self._safe(
            IMAGE_TOOL_GENERATE_SHOW,
            lambda: self._do_generate_show(
                image_generator=image_generator,
                prompt=prompt,
                resolution=resolution,
                negative_prompt=negative_prompt,
                count=count,
                extra=extra,
                mode=mode,
                path=path,
                timeout=timeout,
                reference_images=reference_images,
            ),
        )

    async def _do_generate_show(
        self, *, image_generator: Optional[str] = None, **fields: Any
    ) -> str:
        entry = pick_generator(
            self._entries, image_generator, IMAGE_TOOL_GENERATE_SHOW
        )
        raw = await entry.standard.run_generate_show(
            self._backend,
            self._session_factory,
            self._generate_show_args_cls(**self._generate_show_args(**fields)),
        )
        self._remember_task(raw, entry)
        return raw

    def _generate_args(self, *, reference_images: Optional[List[str]], **fields: Any) -> Dict[str, Any]:
        """后端不支持参考图时不把该键塞进 args（避免被 pydantic 静默丢弃）。"""
        payload: Dict[str, Any] = dict(fields)
        payload["resolution"] = payload.get("resolution") or ""
        if self._with_reference:
            payload["reference_images"] = reference_images
        return payload

    def _generate_show_args(
        self, *, reference_images: Optional[List[str]], **fields: Any
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(fields)
        payload["resolution"] = payload.get("resolution") or ""
        if self._with_reference:
            payload["reference_images"] = reference_images
        return payload

    # ------------------------------------------------------------------
    # 任务归属（多配置下状态/下载工具靠它选回同一份实现）
    # ------------------------------------------------------------------

    def _remember_task(self, raw: str, entry: ImageGenEntry) -> None:
        """记住某个 task_id 由哪个配置提交（结果解析失败则跳过）。"""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            return
        if len(self._task_owner) >= _MAX_TRACKED_TASKS:
            self._task_owner.clear()
        self._task_owner[str(task_id)] = entry.name

    def _entry_for_task(self, task_id: Optional[str]) -> ImageGenEntry:
        """该任务对应的配置；查不到（如进程重启）时回退默认配置。"""
        owner = self._task_owner.get(str(task_id or ""))
        return pick_generator(self._entries, owner, IMAGE_TOOL_GENERATE)

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
    entries: List[ImageGenEntry],
    backend: Optional[BackendProtocol],
    *,
    session_factory: Optional[Callable[[], AsyncSession]] = None,
    enable_standard_tools: bool = True,
    enable_generate_show: bool = False,
) -> ImageGenMiddleware:
    """便捷构造器。"""
    return ImageGenMiddleware(
        entries=entries,
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
