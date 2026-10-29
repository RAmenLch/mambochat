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
from typing import Any, Dict, List, Optional, Tuple

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

IMAGE_TOOL_NAMES: Tuple[str, ...] = (
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_STATUS,
    IMAGE_TOOL_DOWNLOAD,
)

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

_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]+$")
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
    sync: bool = Field(
        default=True,
        description="是否同步等待生成完成；false 时立即返回任务 ID，需用状态工具查询",
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
        default=None, description=f"文件名前缀，缺省为 {DEFAULT_PREFIX}"
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
        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=bool(args.sync),
            extra=extra,
            resolution=resolution,
        )
        task_id = self._require_task_id(payload)
        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": payload.get("status") or ("queued" if not args.sync else "completed"),
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
        if backend is None:
            raise ImageGenToolError(
                "当前会话没有可写的 backend，无法保存图片。请先为该 Agent 挂载一个 Backend。"
            )

        await self._status_until_settled(
            args.task_id, self._clamp_wait_timeout(args.wait_timeout)
        )

        blobs = await self.download(args.task_id, args.index)
        if not blobs:
            raise ImageGenToolError(f"任务 {args.task_id} 没有可下载的图片")

        output_dir, prefix = self._resolve_target(args.path, args.prefix)
        targets = self._build_targets(blobs, output_dir, prefix)

        payloads: List[Tuple[VirtualPath, ImageBlob, bytes]] = [
            (vp, blob, self._decode(blob)) for vp, blob in targets
        ]
        results = await backend.aupload_files(
            [(vp, data) for vp, _, data in payloads]
        )

        files: List[Dict[str, Any]] = []
        errors: List[str] = []
        for (vp, blob, data), res in zip(payloads, results):
            err = getattr(res, "error", None)
            if err is not None:
                errors.append(f"{vp.value}: {getattr(err, 'message', err)}")
                continue
            files.append(
                {
                    "index": blob.index,
                    "path": vp.value,
                    "mime": blob.mime_type,
                    "bytes": len(data),
                }
            )

        if not files:
            raise ImageGenToolError(
                "图片保存失败: " + ("; ".join(errors) if errors else "未知原因")
            )

        result: Dict[str, Any] = {"task_id": args.task_id, "files": files}
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
            if stem and _PREFIX_RE.match(stem):
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
        if not _PREFIX_RE.match(prefix) or len(prefix) > MAX_PREFIX_LEN:
            raise ImageGenToolError(
                "prefix 仅允许字母、数字、下划线和连字符（长度 1~"
                f"{MAX_PREFIX_LEN}），收到: {prefix!r}"
            )
        return prefix

    def _build_targets(
        self, blobs: List[ImageBlob], output_dir: str, prefix: str
    ) -> List[Tuple[VirtualPath, ImageBlob]]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        targets: List[Tuple[VirtualPath, ImageBlob]] = []
        for position, blob in enumerate(blobs):
            suffix = f"_{blob.index}" if len(blobs) > 1 else ""
            filename = f"{prefix}_{stamp}{suffix}{blob.extension}"
            targets.append((VirtualPath(f"{output_dir}/{filename}"), blob))
        return targets

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
