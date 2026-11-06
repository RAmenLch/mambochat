"""生图标准框架的「纯生图接口」实现（``image_api`` 后端）。

只覆盖**纯生图 HTTP 接口**这一种后端：``POST {api_host}/images…``。
具体协议由服务商级执行器（``generation/image_executors/``）决定，
因此本类只做三件事：

* 把契约入参（``prompt`` / ``resolution`` / ``extra`` / ``reference_images``）
  翻译成执行器入参（含模型级默认参数与白名单裁剪）；
* 把执行器异常翻译成 :class:`ImageGenToolError`；
* 复用父类的任务生命周期（磁盘持久化、逐张并发、进度、重试、下载）。

与 chat 后端的差异：``count > 1`` 同样拆成逐张请求，只是每张走执行器而不是 chat/completions。
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.services.generation.image_executors import (
    ExecutorContext,
    ExecutorError,
    ImageApiExecutor,
    ImageRef,
    get_executor,
)

from .model_standard import ChatModelImageGenStandard
from .standard import (
    DEFAULT_WAIT_TIMEOUT,
    ImageGenToolError,
    RefImage,
    parse_resolution,
)


class ImageApiImageGenStandard(ChatModelImageGenStandard):
    """纯生图接口后端（完整实现生图标准三原语）。

    Parameters
    ----------
    executor:
        执行器键（``openai_images`` / ``openrouter_images``）或执行器实例。
    image_options:
        模型级默认参数（``meta_config.image_options``），调用时由 ``extra`` 同名键覆盖。
    capabilities:
        模型能力摘要（``meta_config.image_capabilities``）；存在时用于二次裁剪参数，
        避免下发服务商不支持的字段。
    """

    def __init__(
        self,
        *,
        executor: str | ImageApiExecutor,
        model_id: str,
        api_host: str,
        api_key: str,
        use_proxy: bool = False,
        timeout: Optional[float] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        image_options: Optional[Dict[str, Any]] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        default_count: int = 1,
        default_sync: bool = True,
        default_resolution: str = "",
        default_wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
        supports_reference_images: bool = True,
        generator_name: Optional[str] = None,
    ) -> None:
        # 父类 __init__ 会调用 _resolve_protocol，故先准备好执行器
        self._executor: ImageApiExecutor = (
            get_executor(executor) if isinstance(executor, str) else executor
        )
        self._image_options: Dict[str, Any] = dict(image_options or {})
        self._capabilities: Dict[str, Any] = dict(capabilities or {})
        self._allowed_options, self._options_declared = _resolve_allowed(
            self._executor, self._capabilities
        )

        super().__init__(
            model_id=model_id,
            api_host=api_host,
            api_key=api_key,
            worker_type=self._executor.key,
            protocol=self._executor.key,
            use_proxy=use_proxy,
            timeout=timeout,
            session_factory=session_factory,
            default_count=default_count,
            default_sync=default_sync,
            default_resolution=default_resolution,
            default_wait_timeout=default_wait_timeout,
            supports_reference_images=supports_reference_images,
            generator_name=generator_name,
        )

    # ------------------------------------------------------------------
    # 协议：由执行器决定
    # ------------------------------------------------------------------

    def _resolve_protocol(self, protocol: Optional[str] = None) -> str:
        return self._executor.key

    @property
    def executor(self) -> ImageApiExecutor:
        return self._executor

    @property
    def reference_required(self) -> bool:
        """模型声明 ``input_references.min >= 1`` 时必须带参考图（编辑类模型）。"""
        return self._min_references() is not None and self._min_references() >= 1

    def describe_extra_options(self) -> str:
        """把模型声明的可选参数渲染成一段**确定性**提示（同样的快照 → 同样的字节）。"""
        return _render_extra_options(self._allowed_options, self._capabilities)

    # ------------------------------------------------------------------
    # 单张生成
    # ------------------------------------------------------------------

    async def _generate_one(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        resolution: Optional[str],
        extra: Dict[str, Any],
        reference_images: List[RefImage],
    ) -> Tuple[bytes, str]:
        if self.reference_required and not reference_images:
            minimum = self._min_references() or 1
            raise ImageGenToolError(
                f"该模型要求至少 {minimum} 张参考图（input_references.min={minimum}），"
                "请通过 reference_images 传入工作区图片路径"
            )

        text = self._compose_prompt(prompt, negative_prompt)
        ctx = ExecutorContext(
            model_id=self._model_id,
            prompt=text,
            api_host=self._api_host,
            api_key=self._api_key,
            timeout=self._timeout,
            resolution=parse_resolution(resolution),
            options=self._merge_options(extra),
            references=self._to_refs(reference_images),
        )

        client = await self._client()
        try:
            return await self._executor.generate(client, ctx)
        except ExecutorError as exc:
            raise ImageGenToolError(str(exc)) from exc
        finally:
            await client.aclose()

    # ------------------------------------------------------------------
    # 参数与参考图
    # ------------------------------------------------------------------

    def _merge_options(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """模型级默认参数 ← 调用方 ``extra``，再按执行器能力裁剪。"""
        merged: Dict[str, Any] = dict(self._image_options)
        for key, value in (extra or {}).items():
            if value is None:
                continue
            merged[key] = value
        return {
            key: value
            for key, value in merged.items()
            if key in self._allowed_options and value is not None
        }

    def _min_references(self) -> Optional[int]:
        """模型声明的参考图下限（``input_references.min``）；未声明返回 ``None``。"""
        declared = (self._capabilities or {}).get("supported_parameters")
        if not isinstance(declared, dict):
            return None
        descriptor = declared.get("input_references")
        if not isinstance(descriptor, dict):
            return None
        minimum = descriptor.get("min")
        try:
            return int(minimum) if minimum is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_refs(reference_images: List[RefImage]) -> List[ImageRef]:
        refs: List[ImageRef] = []
        for image in reference_images or []:
            raw = (image.base64_data or "").strip()
            if not raw:
                raise ImageGenToolError("参考图数据为空")
            try:
                data = base64.b64decode(raw, validate=False)
            except (binascii.Error, ValueError) as exc:
                raise ImageGenToolError(f"参考图 base64 无法解码: {exc}") from exc
            if not data:
                raise ImageGenToolError("参考图内容为空")
            refs.append(ImageRef(data=data, mime_type=image.mime_type or "image/png"))
        return refs


# 提示文本的固定上限（超出按确定性规则截断）
_HINT_MAX_CHARS = 320
_HINT_MAX_ENUM_VALUES = 12


def _resolve_allowed(
    executor: ImageApiExecutor, capabilities: Dict[str, Any]
) -> Tuple[frozenset, bool]:
    """执行器白名单 ∩ 模型声明支持的参数。

    Returns
    -------
    (允许的键集合, 模型是否声明了能力)
        模型**没有**声明能力（``supported_parameters`` 缺失或为空）时返回空集：
        宁可不发任何 ``extra`` 键，也不盲猜把不认识的字段发给服务商。
    """
    declared = (capabilities or {}).get("supported_parameters")
    keys: Optional[set] = None
    if isinstance(declared, dict):
        keys = set(declared)
    elif isinstance(declared, list):
        keys = {str(item) for item in declared}
    if not keys:
        return frozenset(), False
    return frozenset(set(executor.whitelist()) & keys), True


def _render_descriptor(name: str, descriptor: Any) -> Optional[str]:
    """把单个能力描述符渲染成稳定文本（同值 → 同文本）。"""
    if name == "size":
        return 'size e.g. "2048x2048" or "2K"'
    if not isinstance(descriptor, dict):
        return name

    kind = str(descriptor.get("type") or "").strip().lower()
    if kind == "enum":
        values = [str(value) for value in (descriptor.get("values") or [])]
        if not values:
            return name
        values = sorted(set(values))
        shown = values[:_HINT_MAX_ENUM_VALUES]
        suffix = ",…" if len(values) > len(shown) else ""
        return f"{name}{{{', '.join(shown)}{suffix}}}"

    if kind == "range":
        lower = descriptor.get("min")
        upper = descriptor.get("max")
        if lower is None and upper is None:
            return name
        if lower is None:
            return f"{name} ≤{upper}"
        if upper is None:
            return f"{name} ≥{lower}"
        return f"{name} {lower}-{upper}"

    if kind == "boolean":
        return None  # 布尔开关没有值域可列，留给模型自行判断
    return name


def _render_extra_options(
    allowed: frozenset, capabilities: Dict[str, Any]
) -> str:
    """渲染 ``extra`` 参数提示。

    确定性要求：键按字母序、枚举值排序、固定分隔符、固定截断规则；不读取任何
    运行时状态、不发网络请求，因此同一份 ``meta_config`` 每次渲染结果完全一致
    （用户不主动改配置，会话前缀就不会变）。
    """
    if not allowed:
        return (
            " 'extra' (image API): this model does not declare supported options, so "
            "unknown keys are ignored — put provider-specific parameters in the prompt "
            "instead of 'extra'."
        )

    declared = (capabilities or {}).get("supported_parameters")
    descriptors = declared if isinstance(declared, dict) else {}
    parts: List[str] = []
    for name in sorted(allowed):
        rendered = _render_descriptor(name, descriptors.get(name))
        if rendered:
            parts.append(rendered)

    if not parts:
        return ""
    body = " | ".join(parts)
    text = f" 'extra' (image API) options: {body}; unsupported keys are ignored."
    if len(text) > _HINT_MAX_CHARS:
        cut = text[: _HINT_MAX_CHARS - 1].rstrip()
        text = f"{cut}…"
    return text


__all__ = ["ImageApiImageGenStandard"]
