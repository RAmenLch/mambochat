"""生图工具标准框架。

定义三个工具的固定契约（``image_generate`` / ``image_task_status`` /
``image_download``），并实现与协议无关的公共逻辑：参数默认值、输出路径
校验与命名、图片落盘、结果 JSON 组装。

子类只需实现三个原语（``submit`` / ``status`` / ``download``），
协议差异（MCP、内置 HTTP 模型等）全部收敛在子类内部。
"""

import asyncio
import base64
import binascii
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from mambo_agents.backends.protocol import BackendProtocol
from mambo_agents.backends.schemas import VirtualPath

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具契约
# ---------------------------------------------------------------------------

IMAGE_TOOL_GENERATE = "image_generate"
IMAGE_TOOL_STATUS = "image_task_status"
IMAGE_TOOL_DOWNLOAD = "image_download"

# 契约三件套（MCP 服务必须实现，也是配置检测的唯一依据）
IMAGE_TOOL_NAMES: Tuple[str, ...] = (
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_STATUS,
    IMAGE_TOOL_DOWNLOAD,
)

# 平台侧「一条龙」工具：生成 → 落盘 → 入库展示，一步完成。
# 它完全由平台包装上面三个原语实现，MCP 服务无需感知。
IMAGE_TOOL_GENERATE_SHOW = "image_generate_show"

# 产出 FILE 子消息的工具（前端据此把结果渲染成文件/图片）。
# show 是通用展示工具，image_generate_show 是一条龙生图工具。
FILE_OUTPUT_TOOLS: Tuple[str, ...] = ("show", IMAGE_TOOL_GENERATE_SHOW)

# 工作区虚拟根：与 show 工具、agent 默认 workspace_root 保持一致
WORKSPACE_ROOT = "/workspace"

DEFAULT_OUTPUT_DIR = f"{WORKSPACE_ROOT}/images"
DEFAULT_PREFIX = "image"
DEFAULT_COUNT = 1
MAX_COUNT = 8
MAX_PREFIX_LEN = 64

# 分辨率参数名（契约字段，形如 1024x1024）
RESOLUTION_ARG = "resolution"
DEFAULT_RESOLUTION = "1024x1024"
MIN_RESOLUTION = 64
MAX_RESOLUTION = 4096

# 状态工具阻塞等待（秒）
DEFAULT_WAIT_TIMEOUT = 0
MAX_WAIT_TIMEOUT = 300
POLL_INTERVAL = 1.5

# 一条龙工具的默认阻塞上限（秒）：未单独配置且未显式传 timeout 时生效
DEFAULT_ONESHOT_WAIT_TIMEOUT = 60

# 文件名生成模式
#   stamp —— 下载时刻的时间戳命名（三件套沿用，行为不变）
#   task  —— 按 task_id 确定性命名（一条龙使用，下载前即可得知路径）
NAMING_STAMP = "stamp"
NAMING_TASK = "task"

# 确定性命名时用于提前规划路径的兜底扩展名；实际下载后以 blob 上报的 mime 为准
DEFAULT_EXT = ".png"

# 文件名片段（前缀 / 由 path 推断的文件名）的非法字符黑名单：只挡会影响
# 路径解析与跨平台文件名合法性的字符，中文等 Unicode 字符一律放行
_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_RESOLUTION_RE = re.compile(r"^\s*(\d{1,4})\s*[xX*×:：]\s*(\d{1,4})\s*$")

_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
}


class ImageGenerateArgs(BaseModel):
    """``image_generate`` 的参数（锁定，不随 server 上报的 schema 变化）。"""

    prompt: str = Field(description="正向提示词，描述期望生成的画面内容")
    resolution: str = Field(
        default=DEFAULT_RESOLUTION,
        description=(
            "图片分辨率，格式为 `宽x高`（单位像素），例如 1024x1024、768x1344；"
            f"取值范围 {MIN_RESOLUTION}~{MAX_RESOLUTION}"
        ),
    )
    negative_prompt: Optional[str] = Field(
        default=None, description="反向提示词，描述不希望出现的内容"
    )
    count: int = Field(
        default=DEFAULT_COUNT, description=f"生成数量，1~{MAX_COUNT}"
    )
    sync: Optional[bool] = Field(
        default=None,
        description=(
            "是否同步等待生成完成；false 时立即返回任务 ID，需用状态工具查询。"
            "不传则使用配置的默认值"
        ),
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "透传给生图后端的额外参数（如 width/height/steps/seed/model 等）。"
            "平台会原样扁平传入，与标准参数同名的键会被忽略"
        ),
    )


class ImageStatusArgs(BaseModel):
    """``image_task_status`` 的参数。"""

    task_id: str = Field(description="``image_generate`` 返回的任务 ID")
    wait_timeout: int = Field(
        default=DEFAULT_WAIT_TIMEOUT,
        description=(
            "阻塞等待秒数，0 表示立即返回当前状态；大于 0 时最多阻塞这么多秒，"
            "任务提前完成（成功/失败/进度 100%）则立即返回"
        ),
    )


class ImageDownloadArgs(BaseModel):
    """``image_download`` 的参数。"""

    task_id: str = Field(description="``image_generate`` 返回的任务 ID")
    index: Optional[int] = Field(
        default=None, description="仅下载指定下标（从 0 开始）的图片；不传则下载全部"
    )
    wait_timeout: int = Field(
        default=DEFAULT_WAIT_TIMEOUT,
        description=(
            "下载前阻塞等待秒数，0 表示不等待；大于 0 时先等任务完成再取图"
        ),
    )
    path: str = Field(
        description=(
            f"目标目录虚拟路径，必填且必须位于 {WORKSPACE_ROOT} 之下"
            f"（例如 {DEFAULT_OUTPUT_DIR}）。缺少或越界会直接报错"
        )
    )
    prefix: Optional[str] = Field(
        default=None,
        description=(
            f"文件名前缀，缺省为 {DEFAULT_PREFIX}。支持中文等 Unicode 字符，"
            '仅禁止 \\ / : * ? " < > | 等路径/文件系统非法字符'
        ),
    )


class ImageGenerateShowArgs(BaseModel):
    """``image_generate_show`` 的参数（一条龙：生成 + 落盘 + 展示）。"""

    prompt: str = Field(description="正向提示词，描述期望生成的画面内容")
    resolution: str = Field(
        default=DEFAULT_RESOLUTION,
        description=(
            "图片分辨率，格式为 `宽x高`（单位像素），例如 1024x1024、768x1344；"
            f"取值范围 {MIN_RESOLUTION}~{MAX_RESOLUTION}"
        ),
    )
    negative_prompt: Optional[str] = Field(
        default=None, description="反向提示词，描述不希望出现的内容"
    )
    count: int = Field(
        default=DEFAULT_COUNT, description=f"生成数量，1~{MAX_COUNT}"
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "透传给生图后端的额外参数（如 width/height/steps/seed/model 等）。"
            "平台会原样扁平传入，与标准参数同名的键会被忽略"
        ),
    )
    mode: Literal["Normal", "Mini_Avatar", "Gal_Avatar", "Group", "Spark"] = Field(
        default="Normal",
        description=(
            "Display mode for the generated image:\n"
            "- Normal: default inline file display\n"
            "- Mini_Avatar: use image as conversation AI avatar\n"
            "- Gal_Avatar: pin image to left side above toolbar, push AI messages right\n"
            "- Group: group consecutive File images, allow user to pin one to top\n"
            "- Spark: hide all other content (text/reasoning/tools), only show Spark + Group files"
        ),
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            f"图片落地目录的虚拟路径，缺省为 {DEFAULT_OUTPUT_DIR}；"
            f"必须位于 {WORKSPACE_ROOT} 之下。若以文件名结尾（如 "
            f"{DEFAULT_OUTPUT_DIR}/fox.png），则目录与文件名前缀会随之推断"
        ),
    )
    timeout: Optional[int] = Field(
        default=None,
        description=(
            "本次等待生成完成的最长秒数；不传则使用配置的等待时长"
            f"（{MAX_WAIT_TIMEOUT} 秒封顶）"
        ),
    )


# ---------------------------------------------------------------------------
# 分辨率解析
# ---------------------------------------------------------------------------


def parse_resolution(value: Any) -> Optional[Tuple[int, int]]:
    """把 ``"1024x1024"`` 之类的分辨率字符串解析为 ``(width, height)``。

    无法识别或越界时返回 ``None``（调用方自行决定降级策略）。
    """
    if value is None:
        return None
    matched = _RESOLUTION_RE.match(str(value))
    if not matched:
        return None
    width, height = int(matched.group(1)), int(matched.group(2))
    if not (MIN_RESOLUTION <= width <= MAX_RESOLUTION):
        return None
    if not (MIN_RESOLUTION <= height <= MAX_RESOLUTION):
        return None
    return width, height


def format_resolution(width: int, height: int) -> str:
    return f"{width}x{height}"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ImageBlob:
    """一张待落盘的图片数据。"""

    index: int
    mime_type: str
    base64_data: str

    @property
    def extension(self) -> str:
        mime = (self.mime_type or "").split(";")[0].strip().lower()
        return _MIME_EXT.get(mime, ".png")


class ImageGenToolError(Exception):
    """生图后端返回的业务错误（可直接展示给 LLM）。"""


def _sanitize_token(value: Any, fallback: str = "task") -> str:
    """把任意 task_id 收敛为可安全用于文件名的片段。"""
    text = str(value or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", text).strip("_")
    return cleaned[:64] or fallback


@dataclass
class ImageTarget:
    """一张图片的确定落盘位置（下载前即可算出）。"""

    path: VirtualPath
    index: int
    mime_type: str
    extension: str


@dataclass
class TargetPlan:
    """落盘路径规划器。

    既可以「下载前预测路径」（``predict``，供“先登记、后落盘”的异步流程使用），
    也可以「拿到真实 blob 后物化路径」（``resolve``，扩展名以 blob 上报的 mime 为准）。

    ``multi`` 显式锁定「是否带多图下标后缀」：异步流程在下载前就已登记路径，
    必须保证之后落盘用的判断一致（否则服务少返回几张图时文件名会对不上）。
    """

    task_id: str
    output_dir: str
    prefix: str
    naming: str
    stamp: str
    ext: Optional[str] = None
    multi: Optional[bool] = None

    def _filename(self, index: int, multi: bool, extension: str) -> str:
        suffix = f"_{index}" if multi else ""
        if self.naming == NAMING_TASK:
            token = _sanitize_token(self.task_id)
        else:
            token = self.stamp
        return f"{self.prefix}_{token}{suffix}{extension}"

    def _is_multi(self, blob_count: int) -> bool:
        return self.multi if self.multi is not None else blob_count > 1

    def resolve(self, blobs: List[ImageBlob]) -> List[Tuple[ImageTarget, ImageBlob]]:
        """按真实 blob 列表物化路径（扩展名取自 blob 的 mime）。

        服务实际产出的张数可能超出预期（例如请求 1 张却返回 2 张）：此时若
        仍不带下标后缀，多张图会撞成同一个文件名互相覆盖，因此统一降级为
        带下标的形式。
        """
        multi = self._is_multi(len(blobs))
        filenames = [self._filename(blob.index, multi, blob.extension) for blob in blobs]
        if len(set(filenames)) != len(filenames):
            multi = True
            filenames = [
                self._filename(blob.index, multi, blob.extension) for blob in blobs
            ]

        resolved: List[Tuple[ImageTarget, ImageBlob]] = []
        for blob, filename in zip(blobs, filenames):
            target = ImageTarget(
                path=VirtualPath(f"{self.output_dir}/{filename}"),
                index=blob.index,
                mime_type=blob.mime_type,
                extension=blob.extension,
            )
            resolved.append((target, blob))
        return resolved

    def predict(self, count: int) -> List[ImageTarget]:
        """不联网地预测 ``count`` 张图片的落盘路径（扩展名取兜底值）。"""
        multi = self._is_multi(count)
        extension = self.ext or DEFAULT_EXT
        return [
            ImageTarget(
                path=VirtualPath(
                    f"{self.output_dir}/{self._filename(index, multi, extension)}"
                ),
                index=index,
                mime_type="",
                extension=extension,
            )
            for index in range(max(1, count))
        ]


@dataclass
class DownloadOutcome:
    """一次下载的结果。"""

    files: List[Dict[str, Any]]
    errors: List[str]
    items: List[Tuple[ImageTarget, bytes]]


def is_settled(payload: Dict[str, Any]) -> bool:
    """任务是否已收敛（完成 / 失败 / 过期 / 进度 100）。

    平台侧后台轮询器驱动「先登记、后落盘」的异步下载时需要这个判断，
    因此在这里提供一个与实现无关的公开入口。
    """
    return ImageGenStandard._is_settled(payload)


# ---------------------------------------------------------------------------
# 标准框架
# ---------------------------------------------------------------------------


class ImageGenStandard(ABC):
    """生图工具标准框架（协议无关）。

    Parameters
    ----------
    default_count:
        未指定 ``count`` 时的默认生成数量。
    default_sync:
        未指定 ``sync`` 时的默认值。
    default_resolution:
        未指定 ``resolution`` 时的默认分辨率，形如 ``1024x1024``。
    default_wait_timeout:
        未指定 ``wait_timeout`` 时的默认阻塞秒数。

    注：图片落地目录完全由 LLM 通过 ``image_download.path`` 指定，
    缺失或越界一律报错，框架不做任何回退。
    """

    def __init__(
        self,
        *,
        default_count: int = DEFAULT_COUNT,
        default_sync: bool = True,
        default_resolution: str = DEFAULT_RESOLUTION,
        default_wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
    ) -> None:
        self._default_count = max(1, min(int(default_count or DEFAULT_COUNT), MAX_COUNT))
        self._default_sync = bool(default_sync)
        self._default_resolution = self._normalize_resolution(default_resolution)
        self._default_wait_timeout = self._clamp_wait_timeout(default_wait_timeout)

    # ------------------------------------------------------------------
    # 子类原语
    # ------------------------------------------------------------------

    @property
    def default_sync(self) -> bool:
        """是否为同步模式（False 时一条龙走「登记 pending + 后台下载」）。"""
        return self._default_sync

    @abstractmethod
    async def submit(
        self,
        prompt: str,
        negative_prompt: Optional[str],
        count: int,
        sync: bool,
        extra: Dict[str, Any],
        resolution: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交生成任务，返回至少包含 ``task_id`` 的字典。

        ``resolution`` 已归一化为 ``宽x高`` 形式（缺省时由框架填入默认值）。
        """

    @abstractmethod
    async def status(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> Dict[str, Any]:
        """查询任务状态，返回至少包含 ``task_id`` / ``status`` 的字典。"""

    @abstractmethod
    async def download(
        self, task_id: str, index: Optional[int] = None
    ) -> List[ImageBlob]:
        """取回任务产出的图片数据。"""

    # ------------------------------------------------------------------
    # 工具入口（中间件直接调用）
    # ------------------------------------------------------------------

    async def run_generate(self, args: ImageGenerateArgs) -> str:
        count = self._clamp_count(args.count)
        resolution = self._normalize_resolution(args.resolution)
        extra = self._merge_extra(args.extra, resolution)
        sync = self._default_sync if args.sync is None else bool(args.sync)
        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=sync,
            extra=extra,
            resolution=resolution,
        )
        task_id = self._require_task_id(payload)
        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": payload.get("status") or ("queued" if not sync else "completed"),
            "count": count,
            "resolution": resolution,
        }
        if payload.get("error"):
            result["error"] = payload["error"]
        return self._dumps(result)

    async def run_status(self, args: ImageStatusArgs) -> str:
        wait_timeout = self._clamp_wait_timeout(args.wait_timeout)
        payload = await self._status_until_settled(args.task_id, wait_timeout)
        result: Dict[str, Any] = {
            "task_id": payload.get("task_id") or args.task_id,
            "status": self._normalize_status(payload.get("status")),
            "progress": self._normalize_progress(payload.get("progress")),
            "count": payload.get("count"),
            "error": payload.get("error"),
        }
        return self._dumps(result)

    async def run_download(
        self, backend: Optional[BackendProtocol], args: ImageDownloadArgs
    ) -> str:
        backend = self._require_backend(backend)

        await self._status_until_settled(
            args.task_id, self._clamp_wait_timeout(args.wait_timeout)
        )

        plan = self.plan_targets(
            task_id=args.task_id,
            path=args.path,
            prefix=args.prefix,
            naming=NAMING_STAMP,
        )
        outcome = await self.download_to(backend, args.task_id, plan, index=args.index)
        if not outcome.files:
            raise ImageGenToolError(
                "图片保存失败: "
                + ("; ".join(outcome.errors) if outcome.errors else "未知原因")
            )

        result: Dict[str, Any] = {"task_id": args.task_id, "files": outcome.files}
        if outcome.errors:
            result["errors"] = outcome.errors
        return self._dumps(result)

    async def run_generate_show(
        self,
        backend: Optional[BackendProtocol],
        session_factory: Optional[Callable[[], Any]],
        args: ImageGenerateShowArgs,
    ) -> str:
        """一条龙：生成 → 等待 → 确定性命名落盘 → 入库 → 返回 file_id。

        异步模式（配置 ``defaultSync=false``）下只提交任务并返回全部确定路径，
        落盘与展示交给平台后台轮询器，LLM 无需再调用其它工具；同步模式下
        超时仍未收敛时不落盘，返回 ``task_id`` 让 LLM 退回三件套继续。
        """
        backend = self._require_backend(backend)
        if session_factory is None:
            raise ImageGenToolError(
                "当前会话无法访问文件库，无法展示生成的图片。请检查服务端配置。"
            )

        count = self._clamp_count(args.count)
        resolution = self._normalize_resolution(args.resolution)
        extra = self._merge_extra(args.extra, resolution)

        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=self._default_sync,
            extra=extra,
            resolution=resolution,
        )
        task_id = self._require_task_id(payload)
        timeout = self._resolve_oneshot_timeout(args.timeout)
        plan = self.plan_targets(
            task_id=task_id,
            path=args.path or DEFAULT_OUTPUT_DIR,
            naming=NAMING_TASK,
            multi=count > 1,
        )

        if not self._default_sync:
            return self._dumps(
                self._pending_result(task_id, plan, count, resolution, timeout, args)
            )

        settled = await self._status_until_settled(task_id, timeout)
        status = self._normalize_status(settled.get("status"))
        if status in ("failed", "expired"):
            raise ImageGenToolError(
                f"生成任务 {task_id} {status}: "
                + str(settled.get("error") or "后端未提供失败原因")
            )
        if not self._is_settled(settled):
            return self._dumps(
                {
                    "task_id": task_id,
                    "status": status,
                    "progress": self._normalize_progress(settled.get("progress")),
                    "count": count,
                    "resolution": resolution,
                    "files": [],
                    "mode": args.mode,
                    "note": (
                        f"生成未在 {timeout} 秒内完成，图片尚未就绪。"
                        "请稍后用 image_task_status(wait_timeout=30) 查询进度，"
                        "完成后再用 image_download 取图并调用 show 展示。"
                    ),
                }
            )

        outcome = await self.download_to(backend, task_id, plan)
        if not outcome.items:
            raise ImageGenToolError(
                "图片保存失败: "
                + ("; ".join(outcome.errors) if outcome.errors else "未知原因")
            )

        from .sink import persist_uploaded

        files, persist_errors = await persist_uploaded(session_factory, outcome.items)
        if not files:
            reason = "; ".join(persist_errors or outcome.errors) or "未知原因"
            raise ImageGenToolError(f"图片入库失败: {reason}")

        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": "completed",
            "count": count,
            "resolution": resolution,
            "mode": args.mode,
            "files": files,
        }
        errors = outcome.errors + persist_errors
        if errors:
            result["errors"] = errors
        return self._dumps(result)

    # ------------------------------------------------------------------
    # 公共工具方法
    # ------------------------------------------------------------------

    def _clamp_count(self, count: Optional[int]) -> int:
        if count is None:
            return self._default_count
        try:
            value = int(count)
        except (TypeError, ValueError):
            return self._default_count
        return max(1, min(value, MAX_COUNT))

    def _merge_extra(
        self, extra: Optional[Dict[str, Any]], resolution: Optional[str] = None
    ) -> Dict[str, Any]:
        """过滤掉与标准参数同名的键，并把分辨率解析为 width/height 合并进去。

        ``extra`` 中显式给出的 ``width`` / ``height`` 优先级高于 ``resolution``。
        """
        reserved = {
            "prompt",
            "negative_prompt",
            "count",
            "sync",
            "task_id",
            "extra",
            "wait_timeout",
            RESOLUTION_ARG,
            # 平台侧参数：仅用于落盘与展示，不该下发给服务
            "mode",
            "path",
            "prefix",
        }
        merged = {k: v for k, v in (extra or {}).items() if k not in reserved}

        size = parse_resolution(resolution)
        if size is not None:
            width, height = size
            merged.setdefault("width", width)
            merged.setdefault("height", height)
        return merged

    @staticmethod
    def _normalize_resolution(value: Any) -> str:
        """把任意输入归一化为 ``宽x高``；无法识别时回退到默认分辨率。"""
        size = parse_resolution(value) or parse_resolution(DEFAULT_RESOLUTION)
        assert size is not None  # DEFAULT_RESOLUTION 必然合法
        return format_resolution(*size)

    @staticmethod
    def _clamp_wait_timeout(value: Any) -> int:
        if value is None:
            return DEFAULT_WAIT_TIMEOUT
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return DEFAULT_WAIT_TIMEOUT
        return max(0, min(seconds, MAX_WAIT_TIMEOUT))

    def _resolve_oneshot_timeout(self, value: Optional[int]) -> int:
        """一条龙的等待上限：显式入参 > 配置项 > 默认 60 秒。"""
        if value is not None:
            return self._clamp_wait_timeout(value)
        if self._default_wait_timeout > 0:
            return self._clamp_wait_timeout(self._default_wait_timeout)
        return self._clamp_wait_timeout(DEFAULT_ONESHOT_WAIT_TIMEOUT)

    def _pending_result(
        self,
        task_id: str,
        plan: TargetPlan,
        count: int,
        resolution: str,
        timeout: int,
        args: ImageGenerateShowArgs,
    ) -> Dict[str, Any]:
        """异步模式的结果：给出全部确定路径，交给平台后台下载并在就绪后展示。

        ``paths`` 里的每个条目都会被前端登记成一条待生成文件；``task_id`` /
        ``prefix`` / ``count`` 让后台轮询器能还原同一套确定性命名去取图。
        """
        predicted = plan.predict(count)
        return {
            "status": "pending",
            "task_id": task_id,
            "path": predicted[0].path.value,
            "paths": [target.path.value for target in predicted],
            "count": count,
            "prefix": plan.prefix,
            "resolution": resolution,
            "timeout": timeout,
            "mode": args.mode,
            "note": (
                f"图片已提交生成（任务 {task_id}），保存与展示由平台在后台完成，"
                f"最多等待 {timeout} 秒；无需再次调用本工具，也不必调用 "
                "image_download / show。若想确认进度可用 image_task_status。"
            ),
        }

    @staticmethod
    def _require_backend(backend: Optional[BackendProtocol]) -> BackendProtocol:
        if backend is None:
            raise ImageGenToolError(
                "当前会话没有可写的 backend，无法保存图片。请先为该 Agent 挂载一个 Backend。"
            )
        return backend

    async def _status_until_settled(
        self, task_id: str, wait_timeout: int
    ) -> Dict[str, Any]:
        """查询状态；``wait_timeout > 0`` 时短轮询直到任务收敛或超时。

        任务进入 ``completed`` / ``failed`` / ``expired``（或进度达到 100）即提前返回。
        后端自身已实现阻塞时，第一次调用就可能直接返回终态，因此不会额外轮询。
        """
        payload = await self.status(task_id, wait_timeout)
        if wait_timeout <= 0 or self._is_settled(payload):
            return payload

        deadline = time.monotonic() + wait_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(POLL_INTERVAL, remaining))
            payload = await self.status(task_id, 0)
            if self._is_settled(payload):
                break
        return payload

    @classmethod
    def _is_settled(cls, payload: Dict[str, Any]) -> bool:
        status = cls._normalize_status((payload or {}).get("status"))
        if status in ("completed", "failed", "expired"):
            return True
        progress = cls._normalize_progress((payload or {}).get("progress"))
        return progress is not None and progress >= 100

    def _resolve_target(
        self,
        raw_path: str,
        raw_prefix: Optional[str],
    ) -> Tuple[str, str]:
        """解析目标目录与前缀。

        ``path`` 缺失或越界一律报错，绝不静默回退到其它目录；
        ``prefix`` 缺省使用默认值，非法时报错。
        """
        directory, inferred_prefix = self._normalize_dir(raw_path)

        prefix = (raw_prefix or "").strip()
        if not prefix and inferred_prefix:
            prefix = inferred_prefix

        return directory, self._normalize_prefix(prefix)

    def _normalize_dir(self, raw_path: str) -> Tuple[str, str]:
        """返回 ``(目录, 从文件名推断的前缀)``，非法输入直接抛错。

        仅接受 ``WORKSPACE_ROOT`` 之下的绝对虚拟路径。
        若传入的是形如 ``/workspace/images/cat.png`` 的文件路径，则拆出
        目录 ``/workspace/images`` 与推断前缀 ``cat``。
        """
        raw = (raw_path or "").strip()
        if not raw:
            raise ImageGenToolError(
                f"image_download 缺少必填参数 path：请指定工作区内的目标目录"
                f"（例如 {DEFAULT_OUTPUT_DIR}）"
            )

        if not raw.startswith("/") or raw.startswith("//") or "\\" in raw or ":" in raw:
            raise ImageGenToolError(
                f"path 必须是绝对虚拟路径且位于 {WORKSPACE_ROOT} 之下，收到: {raw!r}"
            )

        normalized = self._posix_normpath(raw)
        if normalized is None:
            raise ImageGenToolError(
                f"path 不能包含 '..' 越出工作区，收到: {raw!r}"
            )

        file_prefix = ""
        name = normalized.rsplit("/", 1)[-1]
        if "." in name:
            stem = name.rsplit(".", 1)[0]
            parent = normalized.rsplit("/", 1)[0] or WORKSPACE_ROOT
            if stem and not _FILENAME_FORBIDDEN_RE.search(stem):
                file_prefix = stem
            normalized = parent

        if not (normalized == WORKSPACE_ROOT or normalized.startswith(f"{WORKSPACE_ROOT}/")):
            raise ImageGenToolError(
                f"path 必须位于 {WORKSPACE_ROOT} 之下，收到: {raw!r}"
            )

        return normalized, file_prefix

    @staticmethod
    def _posix_normpath(path: str) -> Optional[str]:
        """纯字符串实现的 POSIX 规范化，拒绝 ``..`` 越界。"""
        parts: List[str] = []
        for segment in path.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                if not parts:
                    return None
                parts.pop()
                continue
            parts.append(segment)
        return "/" + "/".join(parts) if parts else "/"

    def _normalize_prefix(self, raw_prefix: str) -> str:
        prefix = (raw_prefix or "").strip()
        if not prefix:
            return DEFAULT_PREFIX
        if _FILENAME_FORBIDDEN_RE.search(prefix) or len(prefix) > MAX_PREFIX_LEN:
            raise ImageGenToolError(
                "prefix 不能包含 \\ / : * ? \" < > | 及控制字符（长度 1~"
                f"{MAX_PREFIX_LEN}），中文等其它字符均可使用，收到: {prefix!r}"
            )
        return prefix

    def plan_targets(
        self,
        *,
        task_id: str,
        path: str,
        prefix: Optional[str] = None,
        naming: str = NAMING_STAMP,
        multi: Optional[bool] = None,
    ) -> TargetPlan:
        """计算落盘路径规划器（纯计算，不联网、不触达 backend）。

        ``path`` 缺失或越界一律报错；``prefix`` 缺省从 path 的文件名推断，
        仍无则用 ``DEFAULT_PREFIX``。``naming=NAMING_TASK`` 时文件名按
        ``task_id`` 确定性生成，可在下载前预测最终路径；此时应同时显式传入
        ``multi``，保证预测与实际落盘的命名判断一致。
        """
        output_dir, resolved_prefix = self._resolve_target(path, prefix)
        return TargetPlan(
            task_id=str(task_id or ""),
            output_dir=output_dir,
            prefix=resolved_prefix,
            naming=naming,
            stamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            multi=multi,
        )

    async def download_to(
        self,
        backend: Optional[BackendProtocol],
        task_id: str,
        plan: TargetPlan,
        *,
        index: Optional[int] = None,
    ) -> DownloadOutcome:
        """按已规划的路径下载并落盘，返回含元信息与原始字节的结果。"""
        backend = self._require_backend(backend)

        blobs = await self.download(task_id, index)
        if not blobs:
            raise ImageGenToolError(f"任务 {task_id} 没有可下载的图片")

        payloads: List[Tuple[ImageTarget, bytes]] = [
            (target, self._decode(blob)) for target, blob in plan.resolve(blobs)
        ]
        results = await backend.aupload_files(
            [(target.path, data) for target, data in payloads]
        )

        files: List[Dict[str, Any]] = []
        errors: List[str] = []
        items: List[Tuple[ImageTarget, bytes]] = []
        for (target, data), res in zip(payloads, results):
            err = getattr(res, "error", None)
            if err is not None:
                errors.append(f"{target.path.value}: {getattr(err, 'message', err)}")
                continue
            files.append(
                {
                    "index": target.index,
                    "path": target.path.value,
                    "mime": target.mime_type,
                    "bytes": len(data),
                }
            )
            items.append((target, data))

        return DownloadOutcome(files=files, errors=errors, items=items)

    @staticmethod
    def _decode(blob: ImageBlob) -> bytes:
        data = (blob.base64_data or "").strip()
        if not data:
            raise ImageGenToolError(f"第 {blob.index} 张图片数据为空")
        try:
            return base64.b64decode(data, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenToolError(
                f"第 {blob.index} 张图片 base64 数据无法解码: {exc}"
            ) from exc

    _STATUS_ALIASES = {
        "pending": "queued",
        "success": "completed",
        "succeeded": "completed",
        "done": "completed",
        "error": "failed",
        "processing": "running",
        "in_progress": "running",
    }

    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return "unknown"
        return cls._STATUS_ALIASES.get(text, text)

    @staticmethod
    def _normalize_progress(value: Any) -> Optional[int]:
        """把 ``50`` / ``"50%"`` / ``"0.5"`` 统一为 0~100 的整数；无法识别时返回 None。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return max(0, min(int(value), 100))
        text = str(value).strip().rstrip("%").strip()
        if not text:
            return None
        try:
            return max(0, min(int(float(text)), 100))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_task_id(payload: Dict[str, Any]) -> str:
        task_id = (payload or {}).get("task_id")
        if not task_id or not str(task_id).strip():
            raise ImageGenToolError(
                "生图后端未返回 task_id，返回内容不符合标准: "
                + json.dumps(payload, ensure_ascii=False)[:500]
            )
        return str(task_id).strip()

    @staticmethod
    def _dumps(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)
