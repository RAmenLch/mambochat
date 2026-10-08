# backend/services/generation/worker/deepseek_file_uploader.py
"""DeepSeek Files API 预上传共享工具与 ``read`` 工具上传钩子。

背景：``read`` 工具读取图片时返回内联 base64 内容块，该 base64 会同时进入
LangGraph checkpoint 与模型请求体（受 48 MiB 请求体 / 32 MiB 单图限制约束）。
本模块提供两类能力：

1. **file_id 缓存与上传**（:func:`resolve_file_id`）：内存 → 数据库 → Files API
   上传三级缓存；进程内与跨请求复用同一张图的 ``file_id``。模型层（``ChatDeepSeek``
   的请求期预取上传）与 ``read`` 预上传钩子共用同一套缓存与 provider_key 公式。
2. **``read`` 预上传钩子**（:class:`DeepSeekFileUploader`）：图片上传成功后在源头替换为
   ``{"type": "file", "file_id": ...}`` 引用块，使 ``ToolMessage``、checkpoint 与历史
   重建只携带小引用；上传失败 / 非图片返回 ``None``（由库回退内联 base64）。

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


async def resolve_file_id(
    client: Any, provider_key: str, mime: str, raw: bytes
) -> Optional[str]:
    """返回图片的 DeepSeek ``file_id``（内存 → 数据库 → 上传）；失败返回 None。

    ``client`` 为 ``openai.AsyncOpenAI`` 实例（复用模型层的 ``root_async_client``，
    继承其代理 / 超时配置）。上传或查库失败一律返回 None，由调用方回退内联 base64。
    """
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
    base64 块；非图片 / 上传失败返回 ``None``（库自动回退内联，不影响 read 结果）。
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
