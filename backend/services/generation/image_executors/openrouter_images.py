"""OpenRouter Images API 执行器。

``POST {api_host}/images``：参数平铺在顶层（不是 chat 侧的 ``image_config``），
响应 ``data[].b64_json`` + ``media_type``，参考图走 ``input_references``。

尺寸语义：``size``（显式像素 / 档位简写）优先，否则用 ``aspect_ratio`` + ``resolution``
（512 / 768 / 1K / 1.5K / 2K / 4K 档位）。服务商不支持时按其文档忽略，不报错。
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Tuple

import httpx

from .base import (
    ExecutorContext,
    ExecutorError,
    ImageApiExecutor,
    aspect_ratio_for,
    decode_base64,
    resolution_tier,
    sniff_mime,
)

IMAGES_PATH = "/images"


class OpenRouterImagesExecutor(ImageApiExecutor):
    key = "openrouter_images"
    label = "OpenRouter Images API"
    supports_reference_images = True
    paths = (IMAGES_PATH,)

    _OPTIONS: FrozenSet[str] = frozenset(
        {
            "size",
            "resolution",
            "aspect_ratio",
            "quality",
            "output_format",
            "background",
            "output_compression",
            "seed",
            "provider",
        }
    )

    def whitelist(self) -> FrozenSet[str]:
        return self._OPTIONS

    async def generate(
        self, client: httpx.AsyncClient, ctx: ExecutorContext
    ) -> Tuple[bytes, str]:
        options = dict(ctx.options or {})
        body: Dict[str, Any] = {
            "model": ctx.model_id,
            "prompt": ctx.prompt,
            "n": 1,
        }

        # 显式像素（size）是权威值：给了 size 就不再派发档位与比例
        if "size" not in options and "resolution" not in options:
            width, height = ctx.size_or_default()
            ratio = aspect_ratio_for(width, height)
            if ratio:
                body["aspect_ratio"] = ratio
            body["resolution"] = resolution_tier(max(width, height))

        body.update(options)

        if ctx.has_references:
            body["input_references"] = [
                {"type": "image_url", "image_url": {"url": ref.data_url}}
                for ref in ctx.references
            ]

        payload = await self.post(
            client,
            self.url(ctx.api_host, IMAGES_PATH),
            headers=self.headers(ctx.api_key),
            json_body=body,
        )
        return self._pick_image(payload)

    @staticmethod
    def _pick_image(payload: Dict[str, Any]) -> Tuple[bytes, str]:
        items = payload.get("data")
        if not isinstance(items, list) or not items:
            raise ExecutorError(_no_image_message(payload))
        first = items[0] if isinstance(items[0], dict) else {}

        encoded = first.get("b64_json")
        if not encoded:
            raise ExecutorError(_no_image_message(payload))

        data = decode_base64(encoded)
        media_type = str(first.get("media_type") or "").strip().lower()
        mime = sniff_mime(data) or (media_type if media_type.startswith("image/") else "")
        return data, mime or "image/png"

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info["endpoints"] = {"generate": IMAGES_PATH}
        return info


def _no_image_message(payload: Dict[str, Any]) -> str:
    error = payload.get("error") if isinstance(payload, dict) else None
    if error:
        message = error.get("message") if isinstance(error, dict) else error
        return f"接口未返回图片: {str(message)[:200]}"
    return "接口未返回图片（data 为空）"


__all__ = ["OpenRouterImagesExecutor", "IMAGES_PATH"]
