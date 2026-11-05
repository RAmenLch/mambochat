"""生图执行器注册表。

执行器与服务商同构：一个 ``AIProvider`` 的 ``worker_type`` 决定它走哪个执行器，
同一服务商下的多个生图模型共用执行器与端点，只有 ``modelId`` 与少量参数不同。

用法::

    from backend.services.generation.image_executors import resolve_executor

    executor = resolve_executor(provider.worker_type, provider.apiHost)
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from .base import (
    DEFAULT_RESOLUTION,
    ExecutorContext,
    ExecutorError,
    ImageApiExecutor,
    ImageRef,
    aspect_ratio_for,
    decode_base64,
    format_size,
    resolution_tier,
    sniff_mime,
)
from .openai_images import OpenAIImagesExecutor
from .openrouter_images import OpenRouterImagesExecutor

#: 服务商 ``worker_type`` → 执行器实例
EXECUTORS: Dict[str, ImageApiExecutor] = {
    executor.key: executor
    for executor in (OpenAIImagesExecutor(), OpenRouterImagesExecutor())
}

#: 生图执行器的 ``worker_type`` 取值集合
IMAGE_WORKERS: FrozenSet[str] = frozenset(EXECUTORS)

#: 兼容写法（``worker_type`` 直接写厂商名时也认）
_ALIASES: Dict[str, str] = {
    "openai": "openai_images",
    "openrouter": "openrouter_images",
}

#: 对话类 worker 中唯一能推导出生图执行器的（OpenAI 兼容网关）
_OPENAI_COMPATIBLE_WORKERS: FrozenSet[str] = frozenset({"openai", "deepseek"})


def is_image_worker(worker_type: Optional[str]) -> bool:
    """该 ``worker_type`` 是否是生图执行器（不能被会话模型使用）。"""
    return (worker_type or "").strip().lower() in IMAGE_WORKERS


def get_executor(key: Optional[str]) -> ImageApiExecutor:
    """按执行器键取实例；未注册时抛 :class:`ExecutorError`。"""
    normalized = (key or "").strip().lower()
    resolved = _ALIASES.get(normalized, normalized)
    executor = EXECUTORS.get(resolved)
    if executor is None:
        raise ExecutorError(
            f"未知的生图执行器 {key!r}（支持: " + " / ".join(sorted(EXECUTORS)) + "）"
        )
    return executor


def resolve_executor(
    worker_type: Optional[str], api_host: Optional[str] = None
) -> ImageApiExecutor:
    """解析服务商应使用的生图执行器。

    1. ``worker_type`` 本身就是生图执行器 → 直接命中；
    2. 否则按 ``api_host`` 推断（含 ``openrouter`` → OpenRouter Images）；
    3. OpenAI 兼容网关（``openai`` / ``deepseek``）→ OpenAI Images API；
    4. 都不匹配 → 抛错，提示为生图单独配置一个服务商。
    """
    key = (worker_type or "").strip().lower()
    if key in EXECUTORS:
        return EXECUTORS[key]

    # 服务商 api_host 先判：OpenRouter 网关与 OpenAI 共用 worker_type=openai
    host = (api_host or "").strip().lower()
    if "openrouter" in host:
        return EXECUTORS["openrouter_images"]

    alias = _ALIASES.get(key)
    if alias:
        return EXECUTORS[alias]

    if not key or key in _OPENAI_COMPATIBLE_WORKERS:
        return EXECUTORS["openai_images"]

    raise ExecutorError(
        f"worker_type={key!r} 无法推导生图执行器；"
        f"请为该生图模型单独配置一个生图服务商（支持: " + " / ".join(sorted(EXECUTORS)) + "）"
    )


__all__ = [
    "DEFAULT_RESOLUTION",
    "EXECUTORS",
    "IMAGE_WORKERS",
    "ExecutorContext",
    "ExecutorError",
    "ImageApiExecutor",
    "ImageRef",
    "aspect_ratio_for",
    "decode_base64",
    "format_size",
    "get_executor",
    "is_image_worker",
    "resolution_tier",
    "resolve_executor",
    "sniff_mime",
]
