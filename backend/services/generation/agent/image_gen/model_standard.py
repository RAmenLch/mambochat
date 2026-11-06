"""生图标准框架的「系统模型」实现（Chat 模型出图）。

只覆盖 **Chat 模型通过对话接口返回图片** 这一类后端：

* ``chat_completions``：OpenAI 兼容网关（OpenRouter 等），
  ``POST {api_host}/chat/completions`` + ``modalities=["image","text"]``；
* ``google_generate_content``：Gemini 原生接口，
  ``POST {api_host}/v1beta/models/{model}:generateContent`` +
  ``generationConfig.responseModalities=["TEXT","IMAGE"]``。

``/images/generations`` 这类纯生图接口不在本实现范围内。

任务状态按标准要求**持久化在磁盘**（``<storage>/image_gen_tasks/<task_id>/``），
生成由进程内 asyncio 任务驱动：``submit`` 立即返回 ``task_id``（``sync=true``
时最多阻塞 90 秒），``status`` / ``download`` 只读磁盘，因此后台轮询器、
平台重跑都能拿到与提交线程一致的结果。
"""

import asyncio
import base64
import binascii
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from .standard import (
    DEFAULT_WAIT_TIMEOUT,
    ImageBlob,
    ImageGenStandard,
    ImageGenToolError,
    RefImage,
    parse_resolution,
)

logger = logging.getLogger(__name__)

# 协议
PROTOCOL_CHAT = "chat_completions"
PROTOCOL_GOOGLE = "google_generate_content"

# worker_type -> 默认协议
_PROTOCOL_BY_WORKER = {
    "google": PROTOCOL_GOOGLE,
    "openai": PROTOCOL_CHAT,
    "deepseek": PROTOCOL_CHAT,
}

# 单次生成的并发上限（count>1 时逐张并发请求）
MAX_CONCURRENCY = 2

# 同步提交的最大阻塞时长（标准建议 ≤ 90 秒）
SYNC_MAX_WAIT = 90

# 单次 HTTP 请求默认超时（秒）
DEFAULT_HTTP_TIMEOUT = 300.0

# 任务目录保留时长（秒）：提交时顺带清理更早的任务
TASK_TTL_SECONDS = 24 * 3600

# queued/running 但进程内已无驱动者、且超过该时长未更新的任务判为中断
STALE_SECONDS = 120

# 状态轮询间隔（秒）
POLL_INTERVAL = 0.5

# Gemini 出图支持的比例（分辨率映射不到时忽略）
_ASPECT_RATIOS: Tuple[Tuple[str, float], ...] = (
    ("1:1", 1.0),
    ("2:3", 2 / 3),
    ("3:2", 3 / 2),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("4:5", 4 / 5),
    ("5:4", 5 / 4),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
    ("21:9", 21 / 9),
)

_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}

_DATA_URL_RE = re.compile(r"data:(image/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)")

# 进程内驱动者登记：仅用于「进程重启后判定任务中断」，状态本身以磁盘为准
_RUNNERS: Dict[str, "asyncio.Task[None]"] = {}

# 任务状态的读-改-写锁（同一 task_id 串行化）
_TASK_LOCKS: Dict[str, asyncio.Lock] = {}


def _lock_for(task_id: str) -> asyncio.Lock:
    lock = _TASK_LOCKS.get(task_id)
    if lock is None:
        lock = asyncio.Lock()
        _TASK_LOCKS[task_id] = lock
    return lock


def _mime_ext(mime: str) -> str:
    return _MIME_EXT.get((mime or "").split(";")[0].strip().lower(), ".png")


def _aspect_ratio_for(resolution: Optional[str]) -> Optional[str]:
    """把 ``宽x高`` 映射到最接近的 Gemini 支持比例（映射不到返回 None）。"""
    size = parse_resolution(resolution)
    if size is None:
        return None
    width, height = size
    target = width / height
    best = min(_ASPECT_RATIOS, key=lambda item: abs(item[1] - target))
    # 比例偏差超过 3% 视为不支持，交给服务用默认值
    if abs(best[1] - target) / target > 0.03:
        return None
    return best[0]


def _is_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _sniff_mime(data: bytes) -> Optional[str]:
    head = data[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if _is_webp(data):
        return "image/webp"
    if head.startswith(b"BM"):
        return "image/bmp"
    return None


class ChatModelImageGenStandard(ImageGenStandard):
    """把系统里已配置的 Chat 模型当作生图后端（完整实现标准三原语）。

    Parameters
    ----------
    model_id:
        模型 ID（``AIModel.modelId``）。
    api_host:
        provider 的 ``apiHost``（OpenAI 兼容网关通常已含 ``/v1``；
        Google 侧可含 ``/v1beta``，这里会归一化）。
    api_key:
        provider 的 ``apiKey``。
    worker_type:
        provider 的 ``worker_type``，用于推导默认协议。
    protocol:
        显式指定协议（``chat_completions`` / ``google_generate_content``），
        缺省按 ``worker_type`` 推导。
    use_proxy:
        是否使用系统代理访问该 provider。
    timeout:
        单次 HTTP 请求超时（秒）。
    session_factory:
        取数据库会话的工厂，用于读取系统代理设置；为空时直连。
    """

    def __init__(
        self,
        *,
        model_id: str,
        api_host: str,
        api_key: str,
        worker_type: str = "openai",
        protocol: Optional[str] = None,
        use_proxy: bool = False,
        timeout: Optional[float] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        default_count: int = 1,
        default_sync: bool = True,
        default_resolution: str = "",
        default_wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
        supports_reference_images: bool = True,
        generator_name: Optional[str] = None,
    ) -> None:
        super().__init__(
            default_count=default_count,
            default_sync=default_sync,
            default_resolution=default_resolution,
            default_wait_timeout=default_wait_timeout,
            supports_reference_images=supports_reference_images,
            generator_name=generator_name,
        )

        self._model_id = (model_id or "").strip()
        if not self._model_id:
            raise ImageGenToolError("生图模型未配置 modelId，无法初始化模型生图后端")

        self._api_host = (api_host or "").strip().rstrip("/")
        self._api_key = (api_key or "").strip()
        self._worker_type = (worker_type or "openai").strip().lower()
        self._protocol = self._resolve_protocol(protocol)
        self._use_proxy = bool(use_proxy)
        self._timeout = float(timeout or DEFAULT_HTTP_TIMEOUT)
        self._session_factory = session_factory
        self._semaphore: Optional[asyncio.Semaphore] = None

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
        reference_images: Optional[List[RefImage]] = None,
    ) -> Dict[str, Any]:
        task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        await self._create_task(
            task_id=task_id,
            count=count,
            resolution=resolution or "",
        )

        runner = asyncio.create_task(
            self._run(
                task_id=task_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                count=count,
                resolution=resolution,
                extra=dict(extra or {}),
                reference_images=list(reference_images or []),
            )
        )
        _RUNNERS[task_id] = runner
        runner.add_done_callback(lambda _t, tid=task_id: _RUNNERS.pop(tid, None))

        if sync:
            try:
                await asyncio.wait_for(
                    asyncio.shield(runner), timeout=self._sync_wait()
                )
            except asyncio.TimeoutError:
                logger.info(
                    "chat 生图 %s 未在 %ss 内完成，回落为异步", task_id, self._sync_wait()
                )

        task = await self._read_task(task_id)
        return {
            "task_id": task_id,
            "status": (task or {}).get("status") or ("completed" if sync else "queued"),
            "count": count,
            "resolution": resolution,
            "error": (task or {}).get("error"),
        }

    async def status(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> Dict[str, Any]:
        payload = await self._snapshot(task_id)
        if wait_timeout <= 0 or self._is_settled(payload):
            return payload

        deadline = time.monotonic() + wait_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(POLL_INTERVAL, remaining))
            payload = await self._snapshot(task_id)
            if self._is_settled(payload):
                break
        return payload

    async def download(
        self, task_id: str, index: Optional[int] = None
    ) -> List[ImageBlob]:
        task = await self._read_task(task_id)
        if task is None:
            raise ImageGenToolError(f"生图任务 {task_id} 不存在或已过期")
        if not self._is_settled(task):
            raise ImageGenToolError(
                f"生图任务 {task_id} 尚未完成（status="
                f"{self._normalize_status(task.get('status'))}）"
            )
        if self._normalize_status(task.get("status")) in ("failed", "expired"):
            raise ImageGenToolError(
                f"生图任务 {task_id} 失败: {task.get('error') or '未知原因'}"
            )

        indexes = sorted(int(i) for i in (task.get("indexes") or []))
        if index is not None:
            indexes = [i for i in indexes if i == int(index)]
        if not indexes:
            raise ImageGenToolError(
                f"任务 {task_id} 没有可取回的图片（可能尚未完成或该 index 无产出）"
            )

        blobs: List[ImageBlob] = []
        for out_index, item in enumerate(indexes):
            data = await self._read_image(task_id, item)
            if data is None:
                continue
            mime = _sniff_mime(data) or (task.get("mime") or "image/png")
            blobs.append(
                ImageBlob(
                    index=out_index if index is None else int(index),
                    mime_type=mime,
                    base64_data=base64.b64encode(data).decode("ascii"),
                )
            )

        if not blobs:
            raise ImageGenToolError(f"任务 {task_id} 的图片文件已丢失，请重新生成")
        return blobs

    # ------------------------------------------------------------------
    # 生成主流程
    # ------------------------------------------------------------------

    async def _run(
        self,
        *,
        task_id: str,
        prompt: str,
        negative_prompt: Optional[str],
        count: int,
        resolution: Optional[str],
        extra: Dict[str, Any],
        reference_images: List[RefImage],
    ) -> None:
        """后台生成 ``count`` 张图，逐张落盘并更新进度。"""
        semaphore = self._get_semaphore()
        total = max(1, int(count))
        errors: List[str] = []

        await self._update_task(
            task_id,
            status="running",
            progress=0,
            count=total,
        )

        async def one(index: int) -> None:
            async with semaphore:
                if task_id not in _RUNNERS:  # 防御：任务已被清理
                    return
                try:
                    data, mime = await self._generate_one(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        resolution=resolution,
                        extra=extra,
                        reference_images=reference_images,
                    )
                except Exception as exc:  # noqa: BLE001 - 单张失败不影响其余
                    errors.append(f"第 {index + 1} 张: {exc}")
                    logger.warning("chat 生图 %s 第 %s 张失败: %s", task_id, index, exc)
                    return

                try:
                    await self._write_image(task_id, index, data, mime)
                except Exception as exc:  # noqa: BLE001 - 落盘失败按失败处理
                    errors.append(f"第 {index + 1} 张写入失败: {exc}")
                    return

                await self._update_task(task_id, add_index=index, mime=mime)

        await asyncio.gather(*(one(i) for i in range(total)))

        task = await self._read_task(task_id) or {}
        produced = list(task.get("indexes") or [])
        if not produced:
            await self._update_task(
                task_id,
                status="failed",
                progress=0,
                error="; ".join(errors) or "模型未返回图片",
            )
            return

        await self._update_task(
            task_id,
            status="completed",
            progress=100,
            error="; ".join(errors) if errors else None,
        )

    async def _generate_one(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        resolution: Optional[str],
        extra: Dict[str, Any],
        reference_images: List[RefImage],
    ) -> Tuple[bytes, str]:
        text = self._compose_prompt(prompt, negative_prompt)
        if self._protocol == PROTOCOL_GOOGLE:
            return await self._generate_google(text, resolution, extra, reference_images)
        return await self._generate_chat(text, resolution, extra, reference_images)

    # ------------------------------------------------------------------
    # 协议：OpenAI 兼容 chat/completions
    # ------------------------------------------------------------------

    async def _generate_chat(
        self,
        text: str,
        resolution: Optional[str],
        extra: Dict[str, Any],
        reference_images: List[RefImage],
    ) -> Tuple[bytes, str]:
        content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
        for image in reference_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.mime_type};base64,{image.base64_data}"
                    },
                }
            )

        body: Dict[str, Any] = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["image", "text"],
            "stream": False,
        }
        body.update(self._passthrough_extra(extra))

        data = await self._post_json("/chat/completions", body)
        url = self._extract_image_url(data)
        if not url:
            raise ImageGenToolError(
                "模型没有返回图片: " + self._message_text(data)
            )
        return await self._fetch_image(url)

    @staticmethod
    def _extract_image_url(data: Dict[str, Any]) -> Optional[str]:
        """兼容各家网关的返回形态，取第一张图的 data URL / http URL。"""
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}

        images = message.get("images")
        if isinstance(images, list):
            for item in images:
                if isinstance(item, dict):
                    image_url = item.get("image_url")
                    if isinstance(image_url, dict) and image_url.get("url"):
                        return str(image_url["url"])
                    if isinstance(image_url, str) and image_url:
                        return image_url
                    if item.get("url"):
                        return str(item["url"])
                elif isinstance(item, str) and item.startswith("data:image/"):
                    return item

        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in ("image_url", "image", "output_image"):
                    image_url = part.get("image_url") or part.get("url")
                    if isinstance(image_url, dict) and image_url.get("url"):
                        return str(image_url["url"])
                    if isinstance(image_url, str) and image_url:
                        return image_url
        elif isinstance(content, str) and "data:image/" in content:
            matched = _DATA_URL_RE.search(content)
            if matched:
                return matched.group(0)
        return None

    @staticmethod
    def _message_text(data: Dict[str, Any]) -> str:
        try:
            message = (data.get("choices") or [])[0].get("message") or {}
        except (IndexError, AttributeError, TypeError):
            return json.dumps(data, ensure_ascii=False)[:300]
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()[:300]
        return json.dumps(data, ensure_ascii=False)[:300]

    # ------------------------------------------------------------------
    # 协议：Google generateContent
    # ------------------------------------------------------------------

    async def _generate_google(
        self,
        text: str,
        resolution: Optional[str],
        extra: Dict[str, Any],
        reference_images: List[RefImage],
    ) -> Tuple[bytes, str]:
        parts: List[Dict[str, Any]] = [{"text": text}]
        for image in reference_images:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": image.mime_type,
                        "data": image.base64_data,
                    }
                }
            )

        generation_config: Dict[str, Any] = {
            "responseModalities": ["TEXT", "IMAGE"],
        }
        aspect = _aspect_ratio_for(resolution)
        if aspect:
            generation_config["imageConfig"] = {"aspectRatio": aspect}
        for key, value in self._passthrough_extra(extra).items():
            generation_config.setdefault(key, value)

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        path = f"/v1beta/models/{self._model_id}:generateContent"
        data = await self._post_json(path, body, google=True)

        parts = self._first_candidate_parts(data)
        texts: List[str] = []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
                return self._decode_base64(str(inline["data"]), mime)
            if isinstance(part.get("text"), str):
                texts.append(part["text"])

        reason = " ".join(texts).strip() or json.dumps(data, ensure_ascii=False)[:300]
        raise ImageGenToolError("模型没有返回图片: " + reason)

    @staticmethod
    def _first_candidate_parts(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            blocked = feedback.get("blockReason")
            if blocked:
                raise ImageGenToolError(f"请求被服务端拒绝: {blocked}")
            return []
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        return [p for p in parts if isinstance(p, dict)]

    # ------------------------------------------------------------------
    # 图片解码 / 下载
    # ------------------------------------------------------------------

    async def _fetch_image(self, url: str) -> Tuple[bytes, str]:
        if url.startswith("data:"):
            matched = _DATA_URL_RE.match(url)
            if not matched:
                raise ImageGenToolError("模型返回的 data URL 无法解析")
            return self._decode_base64(matched.group(2), matched.group(1))

        if not url.startswith(("http://", "https://")):
            raise ImageGenToolError(f"模型返回了无法识别的图片来源: {url[:120]}")

        client = await self._client()
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
            mime = (response.headers.get("content-type") or "").split(";")[0].strip()
        except httpx.HTTPError as exc:
            raise ImageGenToolError(f"下载模型返回的图片失败: {exc}") from exc
        finally:
            await client.aclose()

        if not data:
            raise ImageGenToolError("模型返回的图片内容为空")
        return data, _sniff_mime(data) or (mime or "image/png")

    @staticmethod
    def _decode_base64(raw: str, mime: str) -> Tuple[bytes, str]:
        try:
            data = base64.b64decode(re.sub(r"\s+", "", raw), validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenToolError(f"模型返回的图片 base64 无法解码: {exc}") from exc
        if not data:
            raise ImageGenToolError("模型返回的图片内容为空")
        return data, _sniff_mime(data) or (mime or "image/png")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _post_json(
        self, path: str, body: Dict[str, Any], *, google: bool = False
    ) -> Dict[str, Any]:
        url = f"{self._api_host}{path}"
        headers = {"Content-Type": "application/json"}
        if google:
            headers["x-goog-api-key"] = self._api_key
        else:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client = await self._client()
        try:
            response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ImageGenToolError(
                f"调用生图模型失败: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            await client.aclose()

        if response.status_code >= 400:
            raise ImageGenToolError(
                f"生图模型返回 HTTP {response.status_code}: {self._error_body(response)}"
            )
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ImageGenToolError(
                f"生图模型返回了非 JSON 响应: {response.text[:200]}"
            ) from exc
        if not isinstance(data, dict):
            raise ImageGenToolError("生图模型返回了非预期的响应结构")
        return data

    @staticmethod
    def _error_body(response: httpx.Response) -> str:
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

    async def _client(self) -> httpx.AsyncClient:
        if self._session_factory is None:
            return httpx.AsyncClient(proxy=None, timeout=self._timeout)

        from backend.services.provider_service import _get_http_client_with_proxy

        try:
            async with self._session_factory() as db:
                return await _get_http_client_with_proxy(
                    db, use_proxy_flag=self._use_proxy, timeout=self._timeout
                )
        except Exception as exc:  # noqa: BLE001 - 取代理设置失败不影响直连
            logger.warning("读取代理设置失败，改为直连: %s", exc)
            return httpx.AsyncClient(proxy=None, timeout=self._timeout)

    # ------------------------------------------------------------------
    # 参数处理
    # ------------------------------------------------------------------

    def _resolve_protocol(self, protocol: Optional[str]) -> str:
        explicit = (protocol or "").strip().lower()
        if explicit in (PROTOCOL_CHAT, PROTOCOL_GOOGLE):
            return explicit
        resolved = _PROTOCOL_BY_WORKER.get(self._worker_type)
        if resolved is None:
            raise ImageGenToolError(
                f"worker_type={self._worker_type!r} 不支持模型生图（仅支持 "
                + " / ".join(sorted(_PROTOCOL_BY_WORKER))
                + "）；该服务商没有可用于出图的对话接口"
            )
        return resolved

    @staticmethod
    def _compose_prompt(prompt: str, negative_prompt: Optional[str]) -> str:
        text = (prompt or "").strip()
        negative = (negative_prompt or "").strip()
        if not negative:
            return text
        # Chat 模型没有反向提示词参数，改为在正文里声明要避免的内容
        return f"{text}\n\nAvoid the following in the image: {negative}"

    @staticmethod
    def _passthrough_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
        """``extra`` 原样透传，但丢掉由 resolution 派生的 width/height。

        这两个键在所有网关里都不是合法请求字段，透传只会换来 400；
        需要精确尺寸时用 ``size`` / ``image_config`` 之类的厂商字段。
        """
        return {
            key: value
            for key, value in (extra or {}).items()
            if key not in ("width", "height")
        }

    def _sync_wait(self) -> float:
        return min(self._timeout, float(SYNC_MAX_WAIT))

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        return self._semaphore

    # ------------------------------------------------------------------
    # 任务存储（磁盘，跨进程可见）
    # ------------------------------------------------------------------

    @staticmethod
    def _root() -> Path:
        from backend.services.storage_service import STORAGE_PATH_STR

        return Path(STORAGE_PATH_STR).joinpath("image_gen_tasks")

    def _task_dir(self, task_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(task_id or ""))[:80] or "task"
        return self._root().joinpath(safe)

    def _task_file(self, task_id: str) -> Path:
        return self._task_dir(task_id).joinpath("task.json")

    async def _create_task(
        self, *, task_id: str, count: int, resolution: str
    ) -> None:
        now = time.time()
        task = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "count": count,
            "resolution": resolution,
            "indexes": [],
            "mime": None,
            "error": None,
            "protocol": self._protocol,
            "model": self._model_id,
            "created_at": now,
            "updated_at": now,
        }
        await asyncio.to_thread(self._write_task_file, task_id, task)
        asyncio.create_task(asyncio.to_thread(self._cleanup_expired))

    async def _read_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._read_task_file, task_id)

    async def _update_task(
        self,
        task_id: str,
        *,
        add_index: Optional[int] = None,
        mime: Optional[str] = None,
        **fields: Any,
    ) -> None:
        """读-改-写任务状态；同一任务串行化，避免并发落图互相覆盖。"""
        async with _lock_for(task_id):
            task = self._read_task_file(task_id) or {"task_id": task_id}
            if add_index is not None:
                done = sorted(
                    set(int(i) for i in (task.get("indexes") or [])) | {int(add_index)}
                )
                total = max(1, int(task.get("count") or 1))
                task["indexes"] = done
                fields["progress"] = int(len(done) / total * 100)
            if mime:
                task["mime"] = mime
            task.update(fields)
            task["updated_at"] = time.time()
            await asyncio.to_thread(self._write_task_file, task_id, task)

    async def _write_image(
        self, task_id: str, index: int, data: bytes, mime: str
    ) -> None:
        await asyncio.to_thread(self._write_image_file, task_id, index, data, mime)

    async def _read_image(self, task_id: str, index: int) -> Optional[bytes]:
        return await asyncio.to_thread(self._read_image_file, task_id, index)

    def _read_task_file(self, task_id: str) -> Optional[Dict[str, Any]]:
        path = self._task_file(task_id)
        for attempt in range(4):
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
                return data if isinstance(data, dict) else None
            except FileNotFoundError:
                return None
            except (OSError, json.JSONDecodeError):
                # Windows 上写入方 replace 的瞬间读会拿到 PermissionError
                if attempt == 3:
                    logger.warning("读取生图任务文件失败: %s", path)
                    return None
                time.sleep(0.05)
        return None

    def _write_task_file(self, task_id: str, task: Dict[str, Any]) -> None:
        directory = self._task_dir(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory.joinpath("task.json")
        tmp = directory.joinpath("task.json.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(task, handle, ensure_ascii=False)
        for attempt in range(4):
            try:
                os.replace(tmp, target)
                return
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(0.05)

    def _write_image_file(
        self, task_id: str, index: int, data: bytes, mime: str
    ) -> None:
        directory = self._task_dir(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath(f"{index}{_mime_ext(mime)}").write_bytes(data)

    def _read_image_file(self, task_id: str, index: int) -> Optional[bytes]:
        directory = self._task_dir(task_id)
        for ext in _MIME_EXT.values():
            candidate = directory.joinpath(f"{index}{ext}")
            if candidate.exists():
                try:
                    return candidate.read_bytes()
                except OSError:
                    return None
        return None

    def _cleanup_expired(self) -> None:
        root = self._root()
        if not root.exists():
            return
        deadline = time.time() - TASK_TTL_SECONDS
        for child in root.iterdir():
            try:
                if child.is_dir() and child.stat().st_mtime < deadline:
                    for item in child.iterdir():
                        item.unlink(missing_ok=True)
                    child.rmdir()
            except OSError:
                continue

    async def _snapshot(self, task_id: str) -> Dict[str, Any]:
        task = await self._read_task(task_id)
        if task is None:
            raise ImageGenToolError(f"生图任务 {task_id} 不存在或已过期")

        status = self._normalize_status(task.get("status"))
        if status in ("queued", "running") and task_id not in _RUNNERS:
            stale_after = time.time() - STALE_SECONDS
            if float(task.get("updated_at") or 0) < stale_after:
                await self._update_task(
                    task_id,
                    status="failed",
                    error="生图进程已重启，任务中断，请重新生成",
                )
                task = await self._read_task(task_id) or task

        return {
            "task_id": task.get("task_id") or task_id,
            "status": self._normalize_status(task.get("status")),
            "progress": self._normalize_progress(task.get("progress")),
            "count": task.get("count"),
            "error": task.get("error"),
            "resolution": task.get("resolution"),
            "updated_at": datetime.fromtimestamp(
                float(task.get("updated_at") or 0)
            ).isoformat(timespec="seconds"),
        }


__all__ = [
    "PROTOCOL_CHAT",
    "PROTOCOL_GOOGLE",
    "ChatModelImageGenStandard",
]
