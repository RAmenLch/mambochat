"""生图执行器的基础类型。

执行器（executor）是**服务商级**的生图适配层，与 ``generation/worker/`` 平级：
``worker`` 负责会话生成，执行器负责「怎么发一次生图请求」。

本层刻意不依赖 ``backend.services.generation.agent`` 下的任何东西（工具契约类型、
任务框架），只接收已经归一化的入参、抛自己的 :class:`ExecutorError`，
由 agent 侧的标准实现负责类型与异常翻译。这样依赖方向始终是
``agent → image_executors``，不会反过来。
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import httpx

# 常用分辨率的默认值（宽, 高）
DEFAULT_RESOLUTION: Tuple[int, int] = (1024, 1024)

# aspect_ratio 归一化容差：超过该相对偏差就不猜比例（交由服务商 auto）
_ASPECT_TOLERANCE = 0.03

# OpenRouter 的 resolution 档位（按长边归档）
_RESOLUTION_TIERS: Tuple[Tuple[int, str], ...] = (
    (640, "512"),
    (896, "768"),
    (1152, "1K"),
    (1664, "1.5K"),
    (2688, "2K"),
)


class ExecutorError(Exception):
    """执行器无法完成本次生成（配置错误、接口报错、未返回图片等）。"""


@dataclass(frozen=True)
class ImageRef:
    """参考图（已解码的原始字节 + mime）。"""

    data: bytes
    mime_type: str

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"

    @property
    def extension(self) -> str:
        mime = (self.mime_type or "").lower()
        return {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/gif": "gif",
            "image/bmp": "bmp",
        }.get(mime, "png")


@dataclass
class ExecutorContext:
    """一次生成请求的入参（平台侧已归一化）。"""

    model_id: str
    prompt: str
    api_host: str
    api_key: str
    timeout: float = 300.0
    resolution: Optional[Tuple[int, int]] = None
    options: Dict[str, Any] = field(default_factory=dict)
    references: List[ImageRef] = field(default_factory=list)

    @property
    def has_references(self) -> bool:
        return bool(self.references)

    def size_or_default(self) -> Tuple[int, int]:
        width, height = self.resolution or DEFAULT_RESOLUTION
        return max(1, int(width)), max(1, int(height))


def format_size(resolution: Optional[Tuple[int, int]]) -> str:
    """``(1024, 768)`` → ``"1024x768"``。"""
    width, height = resolution or DEFAULT_RESOLUTION
    return f"{max(1, int(width))}x{max(1, int(height))}"


def aspect_ratio_for(
    width: int,
    height: int,
    allowed: Optional[Tuple[str, ...]] = None,
) -> Optional[str]:
    """把像素尺寸折算成归一化宽高比；偏差过大时返回 ``None``（交给服务商 auto）。"""
    if width <= 0 or height <= 0:
        return None
    candidates = allowed or (
        "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
        "9:16", "16:9", "9:21", "21:9", "1:2", "2:1", "1:4", "4:1", "1:8", "8:1",
    )
    target = width / height
    best: Optional[Tuple[float, str]] = None
    for label in candidates:
        try:
            left, right = label.split(":")
            value = float(left) / float(right)
        except (ValueError, ZeroDivisionError):
            continue
        deviation = abs(value - target) / target
        if best is None or deviation < best[0]:
            best = (deviation, label)
    if best is None or best[0] > _ASPECT_TOLERANCE:
        return None
    return best[1]


def resolution_tier(long_edge: int) -> str:
    """把长边像素归档到 ``512`` / ``768`` / ``1K`` / ``1.5K`` / ``2K`` / ``4K``。"""
    edge = max(1, int(long_edge))
    for limit, tier in _RESOLUTION_TIERS:
        if edge <= limit:
            return tier
    return "4K"


def sniff_mime(data: bytes) -> Optional[str]:
    """按文件头嗅探图片 mime（够用即可，不做完整魔数表）。"""
    if not data:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    head = data[:512].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return "image/tiff"
    return None


def decode_base64(raw: Any) -> bytes:
    """解码接口返回的 base64（兼容 data URL 前缀与空白）。"""
    if isinstance(raw, bytes):
        return raw
    text = str(raw or "").strip()
    if not text:
        raise ExecutorError("接口返回的图片 base64 为空")
    if text.startswith("data:"):
        text = text.split(",", 1)[-1]
    try:
        data = base64.b64decode(re.sub(r"\s+", "", text), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ExecutorError(f"接口返回的图片 base64 无法解码: {exc}") from exc
    if not data:
        raise ExecutorError("接口返回的图片内容为空")
    return data


def error_body(response: httpx.Response) -> str:
    """从错误响应里抽出可读信息（兼容 ``{"error": {"message": ...}}``）。"""
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return (response.text or "")[:300]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        if error:
            return str(error)[:300]
    return json.dumps(payload, ensure_ascii=False)[:300]


class ImageApiExecutor(ABC):
    """纯生图 HTTP 接口的执行器接口。"""

    #: 与 ``AIProvider.worker_type`` 同值的执行器键
    key: str = ""
    #: 前端/检测接口展示用
    label: str = ""
    #: 是否支持参考图（图生图 / 风格参考）
    supports_reference_images: bool = True
    #: 该执行器会使用的端点（相对 ``api_host``）
    paths: Tuple[str, ...] = ()

    @abstractmethod
    def whitelist(self) -> FrozenSet[str]:
        """``extra`` 中允许透传给该执行器的键。"""

    def describe(self) -> Dict[str, Any]:
        """能力摘要（检测接口 / 前端展示）。"""
        return {
            "key": self.key,
            "label": self.label,
            "paths": list(self.paths),
            "supportsReferenceImages": self.supports_reference_images,
            "options": sorted(self.whitelist()),
        }

    @abstractmethod
    async def generate(
        self, client: httpx.AsyncClient, ctx: ExecutorContext
    ) -> Tuple[bytes, str]:
        """发起一次生成，返回 ``(图片字节, mime)``。"""

    # ------------------------------------------------------------------
    # 公共工具
    # ------------------------------------------------------------------

    @staticmethod
    def url(api_host: str, path: str) -> str:
        host = (api_host or "").strip().rstrip("/")
        if not host:
            raise ExecutorError("服务商未配置 API Host")
        return f"{host}{path}"

    @staticmethod
    def headers(api_key: str) -> Dict[str, str]:
        key = (api_key or "").strip()
        if not key:
            raise ExecutorError("服务商未配置 API Key")
        return {"Authorization": f"Bearer {key}"}

    async def post(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        try:
            if files is not None:
                response = await client.post(url, headers=headers, data=data, files=files)
            else:
                response = await client.post(
                    url,
                    headers={**headers, "Content-Type": "application/json"},
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            raise ExecutorError(f"调用生图接口失败: {type(exc).__name__}: {exc}") from exc

        if response.status_code >= 400:
            raise ExecutorError(
                f"生图接口返回 HTTP {response.status_code}: {error_body(response)}"
            )
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ExecutorError(
                f"生图接口返回了非 JSON 响应: {(response.text or '')[:200]}"
            ) from exc
        if not isinstance(payload, dict):
            raise ExecutorError("生图接口返回了非预期的响应结构")
        return payload

    async def fetch_url(self, client: httpx.AsyncClient, url: str) -> Tuple[bytes, str]:
        """接口只给 URL 时把图片下载下来（OpenAI 兼容接口旧行为）。"""
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExecutorError(f"下载生成的图片失败: {type(exc).__name__}: {exc}") from exc
        data = response.content
        if not data:
            raise ExecutorError("下载生成的图片失败: 内容为空")
        mime = sniff_mime(data) or (response.headers.get("content-type") or "image/png").split(";")[0]
        return data, mime
