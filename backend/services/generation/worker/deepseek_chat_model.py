import asyncio
import base64
import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
)
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.utils import from_env, secret_from_env
from langchain_openai import ChatOpenAI
from pydantic import Field, SecretStr, ConfigDict

from backend.config.timezone_config import TZ

logger = logging.getLogger(__name__)

#: DeepSeek Files API 文件有效期（30 天），与 deepseek_file_service.FILE_TTL_SECONDS 一致。
_FILE_TTL_SECONDS = 30 * 24 * 3600

#: 进程内 file_id 缓存：cache_key(provider_key:sha256) -> (file_id, 过期时间戳)。
#: 跨请求复用，避免同一张图被反复上传。
_FILE_ID_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_LOCK = asyncio.Lock()


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


def _cache_get(cache_key: str) -> Optional[str]:
    entry = _FILE_ID_CACHE.get(cache_key)
    if not entry:
        return None
    file_id, expires_ts = entry
    if expires_ts and time.time() >= expires_ts:
        _FILE_ID_CACHE.pop(cache_key, None)
        return None
    return file_id


def _cache_set(cache_key: str, file_id: str, expires_ts: float) -> None:
    _FILE_ID_CACHE[cache_key] = (file_id, expires_ts)


class ChatDeepSeek(ChatOpenAI):
    """
    自定义 DeepSeek Chat 模型（支持 V4）。
    功能说明：
    1. 思考模式(Reasoning)下工具调用(Tool Call)时，回传 reasoning_content。
    2. 支持 DeepSeek V4 的 thinking 参数和 reasoning_effort 参数。
       - thinking: {"type": "enabled"/"disabled"} 控制思考模式开关
       - reasoning_effort: "high"/"max" 控制思考强度
    3. 不对 tool/assistant 消息的 content 做扁平化：DeepSeek 现版本已接受 list content
       （含纯文本块与 image_url 图片块，实测通过），扁平化会剥离 tool 消息中的
       image_url 块，导致 vision 模型（deepseek-v4-flash-vision-exp）无法识图。
    """

    # 默认配置
    deepseek_api_base: str = Field(
        default_factory=from_env("DEEPSEEK_API_BASE", default="https://api.deepseek.com"),
        alias="base_url"
    )
    deepseek_api_key: SecretStr = Field(
        default_factory=secret_from_env("DEEPSEEK_API_KEY", default=None),
        alias="api_key"
    )
    model_name: str = Field(default="deepseek-v4-pro", alias="model")

    # DeepSeek V4 思考模式参数
    thinking: Optional[Dict[str, str]] = Field(
        default=None,
        description='DeepSeek V4 思考模式开关，格式：{"type": "enabled"} 或 {"type": "disabled"}。'
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description='DeepSeek V4 推理强度："high" 或 "max"。'
    )

    model_config = ConfigDict(populate_by_name=True)

    @property
    def _llm_type(self) -> str:
        return "deepseek-chat-custom"

    def _get_request_payload(
            self,
            input_: List[BaseMessage],
            *args,
            **kwargs
    ) -> Dict:
        """
        重写构建请求体的方法。
        """
        # 1. 先降级 DeepSeek 不支持的内容块（如 video，langchain 转换阶段会直接抛错），
        #    再获取 OpenAI 格式的标准 payload。索引与消息类型保持不变，故下方仍可用 input_[i]。
        messages = self._sanitize_messages(input_)
        payload = super()._get_request_payload(messages, *args, **kwargs)

        # 2. 注入 DeepSeek V4 思考模式参数
        # reasoning_effort 是 OpenAI SDK 支持的标准参数（o1/o3 系列也使用）
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        # thinking 是 DeepSeek 扩展参数，必须通过 extra_body 传递，不能直接放在请求体中
        if self.thinking is not None:
            extra_body = payload.get("extra_body", {}) or {}
            extra_body.update({"thinking": self.thinking})
            payload["extra_body"] = extra_body

        # 3. 思考模式与 tool_choice 互斥处理
        # deepseek 思考模式下，tool_choice 指定具体函数名
        # （如 {"type": "function", "function": {"name": "SecurityReviewResult"}}）
        # 会触发 400 报错 "Thinking mode does not support this tool_choice"。
        # 此处在请求体层面自动关闭思考，保证 structured output / 安全审核等场景正常工作。
        tool_choice = payload.get("tool_choice")
        if tool_choice and not isinstance(tool_choice, str):
            extra_body = payload.get("extra_body", {}) or {}
            thinking_cfg = extra_body.get("thinking")
            # thinking_cfg 为 None 时 deepseek 默认开启思考，同样需要显式关闭
            is_thinking_on = thinking_cfg is None or thinking_cfg.get("type") == "enabled"
            if is_thinking_on:
                extra_body["thinking"] = {"type": "disabled"}
                payload["extra_body"] = extra_body

        # 4. 遍历 payload 中的消息进行修复
        for i, payload_msg in enumerate(payload["messages"]):

            # --- 修复: 回传 reasoning_content (解决 400 错误) ---
            # 找到对应的 LangChain 原始消息
            if i < len(input_):
                lc_msg = input_[i]
                if isinstance(lc_msg, AIMessage):
                    # 检查 additional_kwargs 中是否有 reasoning_content
                    reasoning = lc_msg.additional_kwargs.get("reasoning_content")
                    if reasoning:
                        # 显式将 reasoning_content 加回发送给 API 的字典中
                        payload_msg["reasoning_content"] = reasoning

        # 5. 规整媒体块：图片 -> 扁平 file_id（未命中缓存则扁平内联）；非图片文件 -> 文本占位
        self._normalize_media_blocks(payload)

        return payload

    # ------------------------------------------------------------------
    # DeepSeek Files API：把内联 base64 图片改为 file_id 引用
    #
    # 动机：内联图片会计入请求体大小（48 MiB）与单图（32 MiB）限制，大图会导致
    # "Failed to buffer the request body: length limit exceeded"。
    #
    # 分工：async 入口（_astream / _agenerate）做“预取上传”（await，让出事件循环，
    # 不阻塞页面）；同步的 _get_request_payload 只查内存缓存做替换。二者都基于同一份
    # 归一化 payload（user 图与 tool 图都归一为 image_url / file 块），因此覆盖一致。
    # 上传或查库失败一律回退内联。
    # ------------------------------------------------------------------

    def _provider_key(self) -> str:
        """``api_base + api_key`` 的哈希，用于隔离不同 key（DeepSeek 文件归属上传它的 key）。"""
        try:
            key = self.openai_api_key.get_secret_value() if self.openai_api_key is not None else ""
        except Exception:
            key = str(self.openai_api_key or "")
        return hashlib.sha256(f"{self.openai_api_base or ''}|{key}".encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _decode_image_data_url(url: Any) -> Optional[Tuple[str, bytes]]:
        """将 ``data:image/...;base64,...`` 解码为 ``(mime, raw_bytes)``，非图片返回 None。"""
        if not isinstance(url, str) or not url.startswith("data:image/"):
            return None
        try:
            header, b64 = url.split(",", 1)
        except ValueError:
            return None
        if ";base64" not in header:
            return None
        mime = header[len("data:"):].split(";", 1)[0]
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return None
        return mime, raw

    @classmethod
    def _extract_image(cls, block: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
        """从 payload 内容块提取图片原始字节。

        支持两种归一化后的块：``image_url``（内联 data URL）与 ``file``（``file_data``
        为图片 data URL）。分别是用户图与工具图经 langchain 归一化后的形态。
        """
        block_type = block.get("type")
        if block_type == "image_url":
            inner = block.get("image_url")
            url = inner.get("url") if isinstance(inner, dict) else None
            return cls._decode_image_data_url(url)
        if block_type == "file":
            inner = block.get("file")
            if isinstance(inner, dict):
                return cls._decode_image_data_url(inner.get("file_data"))
            return cls._decode_image_data_url(block.get("file_data"))
        return None

    @staticmethod
    def _cache_key(provider_key: str, raw: bytes) -> str:
        return f"{provider_key}:{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def _mime_from_data_url(data_url: Any) -> Optional[str]:
        if not isinstance(data_url, str) or not data_url.startswith("data:"):
            return None
        header = data_url.split(",", 1)[0]
        return header[len("data:"):].split(";", 1)[0] or None

    @staticmethod
    def _iter_content_blocks(payload: Dict[str, Any]):
        for msg in (payload or {}).get("messages", []) or []:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        yield block

    @staticmethod
    def _messages_may_have_images(messages: List[BaseMessage]) -> bool:
        """廉价预判是否含图片块，避免纯文本请求也重复构建 payload。"""
        for msg in messages or []:
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") in ("image", "image_url"):
                    return True
        return False

    def _sanitize_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """把 DeepSeek 无法处理的内容块降级为文本占位，返回（必要时新建的）消息列表。

        langchain 的 ``_format_message_content`` 对 ``video`` 块会直接抛 ``ValueError``；
        而 ``audio`` / ``file`` 会被转成 ``input_audio`` / 嵌套 ``file`` 块，DeepSeek 均不支持。
        故在构建 payload 之前统一降级，避免整个请求失败。索引与消息类型不变，可安全替换。

        注：``audio`` / ``file`` 不在这里处理——它们不会使转换抛错，改由
        :meth:`_normalize_media_blocks` 在 payload 层降级（以便保留图片上传能力）。
        """
        raising_types = {"video", "text-plain"}
        out: List[BaseMessage] = []
        changed = False
        for msg in messages or []:
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                out.append(msg)
                continue
            new_content = []
            modified = False
            for block in content:
                if isinstance(block, dict) and block.get("type") in raising_types:
                    mime = block.get("mime_type") or "未知类型"
                    new_content.append(
                        {"type": "text", "text": f"[附件文件（{mime}）不受当前模型支持，已省略]"}
                    )
                    modified = True
                else:
                    new_content.append(block)
            if modified:
                changed = True
                out.append(msg.model_copy(update={"content": new_content}))
            else:
                out.append(msg)
        return out if changed else messages

    async def _safe_prefetch(self, messages: List[BaseMessage]) -> None:
        try:
            await self._prefetch_images(messages)
        except Exception as e:
            logger.warning(f"[deepseek-files] 图片预取失败，回退内联: {e}")

    async def _prefetch_images(self, messages: List[BaseMessage]) -> None:
        """扫描归一化消息中的图片并逐个解析（内存 → DB → 上传）。"""
        if not self._messages_may_have_images(messages):
            return
        payload = super()._get_request_payload(self._sanitize_messages(messages))
        seen: set = set()
        for block in self._iter_content_blocks(payload):
            info = self._extract_image(block)
            if not info:
                continue
            mime, raw = info
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            await self._resolve_image(mime, raw)

    async def _resolve_image(self, mime: str, raw: bytes) -> Optional[str]:
        """返回图片的 DeepSeek file_id；失败返回 None（调用方保持内联）。"""
        provider_key = self._provider_key()
        digest = hashlib.sha256(raw).hexdigest()
        cache_key = f"{provider_key}:{digest}"

        hit = _cache_get(cache_key)
        if hit:
            return hit

        async with _CACHE_LOCK:
            hit = _cache_get(cache_key)
            if hit:
                return hit

            svc = _svc()
            cached = await svc.get_valid_file_id(provider_key, digest)
            if cached:
                file_id, expires_at = cached
                _cache_set(cache_key, file_id, _to_epoch(expires_at))
                return file_id

            file_id = await self._upload_image_ref(raw, mime)
            if not file_id:
                return None

            ext = (mime.split("/")[-1] or "bin").split("+")[0]
            expires_at = await svc.save_file_id(
                provider_key, digest, file_id, mime, f"image.{ext}", len(raw)
            )
            _cache_set(
                cache_key,
                file_id,
                _to_epoch(expires_at) if expires_at else time.time() + _FILE_TTL_SECONDS,
            )
            return file_id

    async def _upload_image_ref(self, raw: bytes, mime: str) -> Optional[str]:
        """调用 DeepSeek Files API 上传图片，返回 file_id；失败返回 None。"""
        ext = (mime.split("/")[-1] or "bin").split("+")[0]
        try:
            uploaded = await self.root_async_client.files.create(
                file=(f"image.{ext}", raw, mime),
                purpose="user_data",
                expires_after={"anchor": "created_at", "seconds": _FILE_TTL_SECONDS},
            )
            return uploaded.id
        except Exception as e:
            logger.warning(f"[deepseek-files] 上传图片失败，回退内联: {e}")
            return None

    @staticmethod
    def _iter_content_lists(payload: Dict[str, Any]):
        """产出 payload 中每条消息的 content 列表（可原地替换其元素）。"""
        for msg in (payload or {}).get("messages", []) or []:
            if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                yield msg["content"]

    def _normalize_media_blocks(self, payload: Dict[str, Any]) -> None:
        """把 payload 中的媒体块规整为 DeepSeek 可接受的形态。

        注意：只能**替换 payload 列表中的元素**，绝不能原地修改块 dict —— langchain 的
        ``_format_message_content`` 对 ``image_url`` 等块是直接 append 原 dict 引用，
        原地修改会污染原始消息对象/checkpoint，导致下一次请求把 ``{"type":"file","file_id"}``
        重新包装成嵌套 ``{"type":"file","file":{...}}`` 而报 400。

        DeepSeek 的 ``file`` 内容块只支持图片，且只认**扁平**的 ``file_id``/``file_data``：

        - 图片：优先替换为 Files API 的 ``{"type":"file","file_id":...}``（未命中缓存保持不变）。
        - 非图片文件 / 音频：改写为文本占位，避免请求整体失败。
        """
        provider_key = self._provider_key()
        for content in self._iter_content_lists(payload):
            for idx, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                new_block = self._rewrite_media_block(provider_key, block)
                if new_block is not None:
                    content[idx] = new_block

    def _rewrite_media_block(
        self, provider_key: str, block: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """返回替换后的块；None 表示保持原样。"""
        block_type = block.get("type")

        if block_type == "input_audio":
            fmt = (block.get("input_audio") or {}).get("format") or "音频"
            return {"type": "text", "text": f"[附件音频（{fmt}）不受当前模型支持，已省略]"}

        if block_type == "image_url":
            inner = block.get("image_url")
            info = self._decode_image_data_url(
                inner.get("url") if isinstance(inner, dict) else None
            )
            if info:
                file_id = _cache_get(self._cache_key(provider_key, info[1]))
                if file_id:
                    return {"type": "file", "file_id": file_id}
            return None

        if block_type != "file":
            return None

        # 已是扁平 file_id：保持（例如上一轮已被替换、随消息持久化的块）
        if block.get("file_id"):
            return None
        file_data = block.get("file_data")
        filename = block.get("filename")
        if file_data is None:
            inner = block.get("file")
            if not isinstance(inner, dict):
                return None
            if inner.get("file_id"):
                return {"type": "file", "file_id": inner["file_id"]}
            file_data = inner.get("file_data")
            filename = filename or inner.get("filename")
        if file_data is None:
            return None
        return self._flat_file_block(provider_key, file_data, filename)

    def _flat_file_block(
        self, provider_key: str, file_data: str, filename: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """扁平 file_data：图片则用 file_id 或扁平内联；非图片转文本占位。"""
        info = self._decode_image_data_url(file_data)
        if info:
            file_id = _cache_get(self._cache_key(provider_key, info[1]))
            if file_id:
                return {"type": "file", "file_id": file_id}
            flat: Dict[str, Any] = {"type": "file", "file_data": file_data}
            if filename:
                flat["filename"] = filename
            return flat
        mime = self._mime_from_data_url(file_data) or "未知类型"
        return {"type": "text", "text": f"[附件文件（{mime}）不受当前模型支持，已省略]"}

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ):
        await self._safe_prefetch(messages)
        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield chunk

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        await self._safe_prefetch(messages)
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _create_chat_result(
            self, response: Union[Dict, Any], generation_info: Optional[Dict] = None
    ) -> ChatResult:
        """
        处理非流式响应：从 API 响应中提取 reasoning_content 并存入 additional_kwargs。
        """
        rtn = super()._create_chat_result(response, generation_info)

        # 尝试从 response 中提取 reasoning_content
        choices = getattr(response, "choices", [])
        if not choices and isinstance(response, dict):
            choices = response.get("choices", [])

        if choices:
            choice = choices[0]
            message = getattr(choice, "message", None) or choice.get("message", {})

            # 获取 reasoning_content
            reasoning_content = None
            if hasattr(message, "reasoning_content"):
                reasoning_content = message.reasoning_content
            elif isinstance(message, dict):
                reasoning_content = message.get("reasoning_content")

            # 如果存在，存入 additional_kwargs
            if reasoning_content:
                rtn.generations[0].message.additional_kwargs["reasoning_content"] = reasoning_content

        return rtn

    def _convert_chunk_to_generation_chunk(
            self,
            chunk: Dict,
            default_chunk_class: Any,
            base_generation_info: Optional[Dict]
    ) -> Optional[ChatGenerationChunk]:
        """
        处理流式响应：从 Chunk 中提取 reasoning_content 的增量。
        """
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )

        if not generation_chunk:
            return None

        # 尝试从 chunk delta 中提取 reasoning_content
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            reasoning_content = delta.get("reasoning_content")

            if reasoning_content:
                # 将 reasoning_content 放入 additional_kwargs
                generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content

        return generation_chunk
