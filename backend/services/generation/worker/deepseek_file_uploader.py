# backend/services/generation/worker/deepseek_file_uploader.py
"""DeepSeek Files API 预上传共享工具与 ``read`` 工具上传钩子。

背景：``read`` 工具读取图片时返回内联 base64 内容块，该 base64 会同时进入
LangGraph checkpoint 与模型请求体（受 48 MiB 请求体 / 32 MiB 单图限制约束）。
本模块提供三类能力：

1. **file_id 缓存与上传**（:func:`resolve_file_id`）：内存 → 数据库 → Files API
   上传三级缓存；进程内与跨请求复用同一张图的 ``file_id``。模型层（``ChatDeepSeek``
   的请求期预取上传）与 ``read`` 预上传钩子共用同一套缓存与 provider_key 公式。
2. **``read`` 预上传钩子**（:class:`DeepSeekFileUploader`）：图片上传成功后在源头替换为
   ``{"type": "file", "file_id": ...}`` 引用块，使 ``ToolMessage``、checkpoint 与历史
   重建只携带小引用；上传失败 / 非图片返回 ``None``（由库回退内联 base64）。
3. **图片可用性兜底**（:func:`unsupported_image_reason`）：视觉模型对超尺寸 / 非法图片
   会整包 400（``You have uploaded an unsupported image``），把整轮生成打成 failed。
   故上传前先校验，不合法的一律降级为文本占位块（``unsupported_image_block``），
   既不写缓存也不进上下文。

引用块不再携带 base64，而前端展示 / 落库仍需要原始内容：上传成功时经
:func:`stash_raw` 暂存 ``file_id -> 原始内容``，工具结果解码（``DefaultLangChainDecode``）
时经 :func:`restore_media_block` 按 ``file_id`` 还原为内联媒体块，后续
``SaveAndPersistFile`` / ``MultimodalMedia`` 管道保持不变。
"""

import asyncio
import base64
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.config.timezone_config import TZ

logger = logging.getLogger(__name__)

#: DeepSeek Files API 文件有效期（30 天），与 deepseek_file_service.FILE_TTL_SECONDS 一致。
FILE_TTL_SECONDS = 30 * 24 * 3600

#: 进程内 file_id 缓存：cache_key(provider_key:sha256) -> (file_id, 过期时间戳)。
#: 跨请求复用，避免同一张图被反复上传。
_FILE_ID_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_LOCK = asyncio.Lock()

#: 原始内容暂存：file_id -> (file_type, mime_type, base64_content)。
#: 供工具结果落库时还原 base64（引用块本身不再携带原始内容）。
_STASH: "OrderedDict[str, Tuple[str, str, str]]" = OrderedDict()
_STASH_LOCK = threading.Lock()
_STASH_MAX_ENTRIES = 32
_STASH_MAX_CHARS = 64 * 1024 * 1024  # base64 字符数上限（约 48 MiB 原始数据）


def _svc():
    """延迟导入上传缓存服务，避免模块级循环依赖。"""
    from backend.services import deepseek_file_service
    return deepseek_file_service


def _to_epoch(dt: Optional[datetime]) -> float:
    """datetime -> epoch 秒；naive 时间按配置时区视为本地时间。"""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = TZ.localize(dt)
    return dt.timestamp()


def provider_key_of(api_base: str, api_key: str) -> str:
    """``api_base + api_key`` 的哈希，用于隔离不同 key（DeepSeek 文件归属上传它的 key）。

    与 ``ChatDeepSeek._provider_key()`` 为同一公式（调用方传入的 ``api_base`` 须
    与模型构造时的 ``base_url`` 完全一致），保证模型层、钩子层与历史重建层
    命中同一份上传缓存。
    """
    return hashlib.sha256(f"{api_base or ''}|{api_key or ''}".encode("utf-8")).hexdigest()[:32]


def cache_key_of(provider_key: str, raw: bytes) -> str:
    """按内容摘要生成进程内缓存键。"""
    return f"{provider_key}:{hashlib.sha256(raw).hexdigest()}"


def get_cached_file_id(cache_key: str) -> Optional[str]:
    """查进程内缓存（过期即失效）；未命中返回 None。"""
    entry = _FILE_ID_CACHE.get(cache_key)
    if not entry:
        return None
    file_id, expires_ts = entry
    if expires_ts and time.time() >= expires_ts:
        _FILE_ID_CACHE.pop(cache_key, None)
        return None
    return file_id


def set_cached_file_id(cache_key: str, file_id: str, expires_ts: float) -> None:
    _FILE_ID_CACHE[cache_key] = (file_id, expires_ts)


# ----------------------------------------------------------------------
# 图片可用性兜底：视觉模型不接受的图片一律降级为文本占位
#
# 背景：DeepSeek 对"格式合法但不可用"的图片（超大尺寸等）会整包返回 400
# ``.messages[N].image[0]: You have uploaded an unsupported image``，
# 该错误会沿 tool -> pregel -> manager 冒泡，把整轮生成打成 failed。
# 例：子代理 read 了一张 2412x20211 的 matplotlib PNG 直接炸掉整轮。
# 故在上传前（以及请求期归一化时）做尺寸/格式校验，不合法就换成文本占位。
# ----------------------------------------------------------------------

#: 单边像素上限（超过则视为视觉模型不可用）
MAX_IMAGE_SIDE = 8000

#: 总像素上限（约 40 MP；常规截图/图表在 1~5 MP，超大画布才会触发）
MAX_IMAGE_PIXELS = 40_000_000

#: 视觉模型支持的图片 MIME
SUPPORTED_IMAGE_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
)


def sniff_image_size(raw: bytes) -> Optional[Tuple[str, int, int]]:
    """从文件头解析 ``(mime, width, height)``。

    只依赖标准库（不引入 Pillow）：支持 PNG / GIF / JPEG / WebP。
    无法识别时返回 None，尺寸解析不出来时返回宽高为 0 的元组。
    """
    if not raw:
        return None

    # PNG: 签名 8B + IHDR(宽 4B、高 4B，大端)
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 24:
        return (
            "image/png",
            int.from_bytes(raw[16:20], "big"),
            int.from_bytes(raw[20:24], "big"),
        )

    # GIF: 签名 6B + 逻辑屏宽/高（小端 2B）
    if raw[:6] in (b"GIF87a", b"GIF89a") and len(raw) >= 10:
        return (
            "image/gif",
            int.from_bytes(raw[6:8], "little"),
            int.from_bytes(raw[8:10], "little"),
        )

    # WebP: RIFF....WEBP + 子块（VP8X 画布 / VP8 有损 / VP8L 无损）
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" and len(raw) >= 30:
        chunk = raw[12:16]
        if chunk == b"VP8X":
            return (
                "image/webp",
                int.from_bytes(raw[24:27], "little") + 1,
                int.from_bytes(raw[27:30], "little") + 1,
            )
        if chunk == b"VP8 ":
            return (
                "image/webp",
                int.from_bytes(raw[26:28], "little") & 0x3FFF,
                int.from_bytes(raw[28:30], "little") & 0x3FFF,
            )
        if chunk == b"VP8L" and len(raw) >= 25:
            bits = int.from_bytes(raw[21:25], "little")
            return "image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        return "image/webp", 0, 0

    # JPEG: 逐段扫描 SOFn 取高宽
    if raw[:2] == b"\xff\xd8":
        i, n = 2, len(raw)
        while i + 9 < n:
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = int.from_bytes(raw[i + 2:i + 4], "big")
            if seg_len < 2:
                return None
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return (
                    "image/jpeg",
                    int.from_bytes(raw[i + 7:i + 9], "big"),
                    int.from_bytes(raw[i + 5:i + 7], "big"),
                )
            i += 2 + seg_len
        return "image/jpeg", 0, 0

    return None


def unsupported_image_reason(mime: str, raw: bytes) -> Optional[str]:
    """判断图片能否交给视觉模型；可用返回 None，不可用返回中文原因。

    判定项：MIME 白名单、文件内容可解析、单边 / 总像素上限。
    """
    normalized = (mime or "").split(";")[0].strip().lower()
    if normalized not in SUPPORTED_IMAGE_MIMES:
        return f"格式 {normalized or '未知'} 不受支持"

    sniffed = sniff_image_size(raw)
    if sniffed is None:
        return "文件内容不是有效的图片"

    _, width, height = sniffed
    if width <= 0 or height <= 0:
        return "无法解析图片尺寸"
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
        return f"尺寸 {width}×{height} 超过单边 {MAX_IMAGE_SIDE}px 上限"
    if width * height > MAX_IMAGE_PIXELS:
        return (
            f"尺寸 {width}×{height} 超过 "
            f"{MAX_IMAGE_PIXELS // 1_000_000}M 像素上限"
        )
    return None


def unsupported_image_block(reason: str) -> Dict[str, Any]:
    """把不可用图片降级成的文本内容块。"""
    return {"type": "text", "text": f"[图片不可用（{reason}），已省略]"}


#: 引用块（file_id）校验结果缓存：file_id -> 不可用原因（None 表示可用）。
#: 避免每次请求都重复解码同一张图的 base64。
_IMAGE_REASON_CACHE: Dict[str, Optional[str]] = {}
_IMAGE_REASON_CACHE_MAX = 256


def stashed_image_reason(file_id: str) -> Optional[str]:
    """按引用块 ``file_id`` 取暂存的原始内容做兜底校验。

    取不到原始内容（进程重启 / 条目被淘汰）返回 None —— 这类历史引用无法回溯，
    交由上传前校验挡住新增的坏图。结果按 ``file_id`` 缓存。
    """
    if not file_id:
        return None
    if file_id in _IMAGE_REASON_CACHE:
        return _IMAGE_REASON_CACHE[file_id]

    entry = get_stashed_raw(file_id)
    if entry is None:
        return None

    _, mime, base64_content = entry
    try:
        raw = base64.b64decode(base64_content)
    except Exception:
        return None

    reason = unsupported_image_reason(mime, raw)
    if len(_IMAGE_REASON_CACHE) >= _IMAGE_REASON_CACHE_MAX:
        _IMAGE_REASON_CACHE.clear()
    _IMAGE_REASON_CACHE[file_id] = reason
    return reason


async def resolve_file_id(
    client: Any, provider_key: str, mime: str, raw: bytes
) -> Optional[str]:
    """返回图片的 DeepSeek ``file_id``（内存 → 数据库 → 上传）；失败返回 None。

    ``client`` 为 ``openai.AsyncOpenAI`` 实例（复用模型层的 ``root_async_client``，
    继承其代理 / 超时配置）。上传或查库失败一律返回 None，由调用方回退内联 base64。

    不受支持的图片（格式 / 尺寸超限）直接返回 None：既不上传也不入缓存，避免污染
    ``DeepSeekFileCache``（缓存命中后会被反复塞进请求，导致每次都 400）。
    """
    reason = unsupported_image_reason(mime, raw)
    if reason:
        logger.warning(f"[deepseek-files] 跳过不受支持的图片上传（{reason}）")
        return None

    digest = hashlib.sha256(raw).hexdigest()
    # 注意：cache_key_of 接收原始内容（内部自行取 sha256），不能传 hex 摘要字符串。
    cache_key = cache_key_of(provider_key, raw)

    hit = get_cached_file_id(cache_key)
    if hit:
        return hit

    async with _CACHE_LOCK:
        hit = get_cached_file_id(cache_key)
        if hit:
            return hit

        svc = _svc()
        cached = await svc.get_valid_file_id(provider_key, digest)
        if cached:
            file_id, expires_at = cached
            set_cached_file_id(cache_key, file_id, _to_epoch(expires_at))
            return file_id

        file_id = await _upload_file(client, raw, mime)
        if not file_id:
            return None

        ext = (mime.split("/")[-1] or "bin").split("+")[0]
        expires_at = await svc.save_file_id(
            provider_key, digest, file_id, mime, f"image.{ext}", len(raw)
        )
        set_cached_file_id(
            cache_key,
            file_id,
            _to_epoch(expires_at) if expires_at else time.time() + FILE_TTL_SECONDS,
        )
        return file_id


async def _upload_file(client: Any, raw: bytes, mime: str) -> Optional[str]:
    """调用 DeepSeek Files API 上传图片，返回 file_id；失败返回 None。"""
    ext = (mime.split("/")[-1] or "bin").split("+")[0]
    try:
        uploaded = await client.files.create(
            file=(f"image.{ext}", raw, mime),
            purpose="user_data",
            expires_after={"anchor": "created_at", "seconds": FILE_TTL_SECONDS},
        )
        return uploaded.id
    except Exception as e:
        logger.warning(f"[deepseek-files] 上传图片失败，回退内联: {e}")
        return None


# ----------------------------------------------------------------------
# 原始内容暂存：引用块（file_id）-> 内联媒体块（base64）的还原
# ----------------------------------------------------------------------

def stash_raw(
    file_id: str, mime_type: str, base64_content: str, file_type: str = "image"
) -> None:
    """暂存 ``file_id`` 对应的原始内容，供工具结果落库时还原 base64。"""
    if not file_id or not base64_content:
        return
    with _STASH_LOCK:
        _STASH[file_id] = (
            file_type,
            mime_type or "application/octet-stream",
            base64_content,
        )
        _STASH.move_to_end(file_id)
        total = sum(len(entry[2]) for entry in _STASH.values())
        while len(_STASH) > 1 and (
            len(_STASH) > _STASH_MAX_ENTRIES or total > _STASH_MAX_CHARS
        ):
            _, evicted = _STASH.popitem(last=False)
            total -= len(evicted[2])


def get_stashed_raw(file_id: str) -> Optional[Tuple[str, str, str]]:
    """读取暂存条目（不删除）；返回 ``(file_type, mime_type, base64_content)``。"""
    if not file_id:
        return None
    with _STASH_LOCK:
        entry = _STASH.get(file_id)
        if entry is not None:
            _STASH.move_to_end(file_id)
        return entry


def restore_media_block(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """引用块还原为内联媒体块（``{"type", "base64", "mime_type"}``）。

    支持扁平 ``{"type": "file", "file_id": ...}`` 与嵌套 ``{"file": {"file_id": ...}}``
    两种形态。找不到暂存（如进程重启、条目被淘汰）返回 None，调用方跳过该块。
    """
    if not isinstance(block, dict):
        return None
    file_id = block.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        inner = block.get("file")
        file_id = inner.get("file_id") if isinstance(inner, dict) else None
    if not isinstance(file_id, str) or not file_id:
        return None
    entry = get_stashed_raw(file_id)
    if entry is None:
        return None
    file_type, mime_type, base64_content = entry
    return {"type": file_type, "base64": base64_content, "mime_type": mime_type}


# ----------------------------------------------------------------------
# read 工具预上传钩子
# ----------------------------------------------------------------------

class DeepSeekFileUploader:
    """``read`` 工具预上传钩子（``mambo_agents.backends.protocol.FileUploader`` 契约）。

    异步回调：图片上传成功后返回 ``[{"type": "file", "file_id": ...}]`` 替换内联
    base64 块；非图片返回 ``None``（库自动回退内联，不影响 read 结果）。

    不受支持的图片（格式 / 尺寸超限）返回 **文本占位块** 而不是 ``None``：
    回退内联 base64 同样会被视觉模型 400 拒绝，必须让这张图完全不进入
    ToolMessage / checkpoint / 后续请求。
    """

    def __init__(self, client: Any, provider_key: str) -> None:
        self._client = client
        self._provider_key = provider_key

    async def __call__(
        self,
        file_path: Any,
        base64_content: str,
        mime_type: str,
    ) -> Optional[List[Dict[str, Any]]]:
        if not (mime_type or "").startswith("image/"):
            return None
        try:
            raw = base64.b64decode(base64_content)
        except Exception as e:
            logger.warning(f"[deepseek-files] 预上传解码 base64 失败，回退内联: {e}")
            return None

        reason = unsupported_image_reason(mime_type, raw)
        if reason:
            logger.warning(
                f"[deepseek-files] read 读取的图片不受支持（{reason}），已降级为文本占位：{file_path}"
            )
            return [unsupported_image_block(reason)]

        file_id = await resolve_file_id(self._client, self._provider_key, mime_type, raw)
        if not file_id:
            return None

        stash_raw(file_id, mime_type, base64_content)
        return [{"type": "file", "file_id": file_id}]


def build_file_uploader_for_model(model: Any) -> Optional[DeepSeekFileUploader]:
    """为 DeepSeek 模型构建 ``read`` 预上传钩子；其他 provider 返回 None（不启用）。"""
    try:
        from backend.services.generation.worker.deepseek_chat_model import ChatDeepSeek
    except Exception:
        return None
    if not isinstance(model, ChatDeepSeek):
        return None
    return DeepSeekFileUploader(
        client=model.root_async_client,
        provider_key=model._provider_key(),
    )
