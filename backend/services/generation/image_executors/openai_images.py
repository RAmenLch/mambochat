"""OpenAI Images API 执行器。

* 纯文生图：``POST {api_host}/images/generations``（JSON）
* 图生图：  ``POST {api_host}/images/edits``（multipart，``image[]`` + ``prompt``）

响应取 ``data[].b64_json``；只有 ``url`` 时下载取字节。``response_format`` 不默认下发
（gpt-image-* 不接受该字段），需要时通过 ``image_options.response_format`` 显式传。
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import httpx

from .base import (
    ExecutorContext,
    ExecutorError,
    ImageApiExecutor,
    decode_base64,
    format_size,
    sniff_mime,
)

GENERATIONS_PATH = "/images/generations"
EDITS_PATH = "/images/edits"


class OpenAIImagesExecutor(ImageApiExecutor):
    key = "openai_images"
    label = "OpenAI Images API"
    supports_reference_images = True
    paths = (GENERATIONS_PATH, EDITS_PATH)

    _OPTIONS: FrozenSet[str] = frozenset(
        {
            "quality",
            "background",
            "output_format",
            "output_compression",
            "moderation",
            "response_format",
            "user",
        }
    )

    def whitelist(self) -> FrozenSet[str]:
        return self._OPTIONS

    async def generate(
        self, client: httpx.AsyncClient, ctx: ExecutorContext
    ) -> Tuple[bytes, str]:
        size = format_size(ctx.size_or_default())
        options = dict(ctx.options or {})
        if ctx.has_references:
            payload = await self._edit(client, ctx, size, options)
        else:
            payload = await self._generation(client, ctx, size, options)
        return await self._pick_image(client, payload)

    # ------------------------------------------------------------------
    # 两个端点
    # ------------------------------------------------------------------

    async def _generation(
        self,
        client: httpx.AsyncClient,
        ctx: ExecutorContext,
        size: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": ctx.model_id,
            "prompt": ctx.prompt,
            "n": 1,
            "size": size,
        }
        body.update(options)
        return await self.post(
            client,
            self.url(ctx.api_host, GENERATIONS_PATH),
            headers=self.headers(ctx.api_key),
            json_body=body,
        )

    async def _edit(
        self,
        client: httpx.AsyncClient,
        ctx: ExecutorContext,
        size: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        form: Dict[str, Any] = {
            "model": ctx.model_id,
            "prompt": ctx.prompt,
            "n": "1",
            "size": size,
        }
        form.update({key: str(value) for key, value in options.items()})

        files: List[Tuple[str, Tuple[str, bytes, str]]] = []
        for index, reference in enumerate(ctx.references):
            files.append(
                (
                    "image[]",
                    (
                        f"reference_{index}.{reference.extension}",
                        reference.data,
                        reference.mime_type,
                    ),
                )
            )
        if not files:
            raise ExecutorError("图生图需要至少一张参考图")

        return await self.post(
            client,
            self.url(ctx.api_host, EDITS_PATH),
            headers=self.headers(ctx.api_key),
            data=form,
            files=files,
        )

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    async def _pick_image(
        self, client: httpx.AsyncClient, payload: Dict[str, Any]
    ) -> Tuple[bytes, str]:
        items = payload.get("data")
        if not isinstance(items, list) or not items:
            raise ExecutorError(_no_image_message(payload))
        first = items[0] if isinstance(items[0], dict) else {}

        encoded = first.get("b64_json")
        if encoded:
            data = decode_base64(encoded)
            return data, sniff_mime(data) or "image/png"

        url = first.get("url")
        if url:
            return await self.fetch_url(client, str(url))

        raise ExecutorError(_no_image_message(payload))

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info["endpoints"] = {
            "generate": GENERATIONS_PATH,
            "edit": EDITS_PATH,
        }
        return info


def _no_image_message(payload: Dict[str, Any]) -> str:
    text = payload.get("error") if isinstance(payload, dict) else None
    if text:
        return f"接口未返回图片: {str(text)[:200]}"
    return "接口未返回图片（data 为空）"


__all__ = ["OpenAIImagesExecutor", "GENERATIONS_PATH", "EDITS_PATH"]
