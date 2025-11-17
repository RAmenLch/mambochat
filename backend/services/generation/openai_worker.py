# backend/services/generation/openai_worker.py
import httpx
import json
from typing import AsyncGenerator, Dict, Any, List

from .base import AbstractGenerateWorker
from .llm_io import LLMInput, WorkerOutput


def get_reason(delta: dict) -> str:
    """从响应块中安全地提取 'reasoning' 内容。"""
    return delta.get("reasoning_content") or delta.get("reasoning")


class OpenAIGenerateWorker(AbstractGenerateWorker):
    """
    OpenAI 生成工作者，负责与 OpenAI 兼容的 API 交互。
    能够处理文本和图片等多模态内容的输入与输出，并生成标准化的 WorkerOutput 流。
    """

    async def _process_images(self, images: List[Dict[str, Any]]) -> AsyncGenerator[WorkerOutput, None]:
        """处理响应中的图片数据并生成 WorkerOutput。"""
        if not isinstance(images, list):
            return
        for image_data in images:
            if isinstance(image_data, dict) and image_data.get("type") == "image_url":
                image_url_obj = image_data.get("image_url")
                if isinstance(image_url_obj, dict):
                    url = image_url_obj.get("url")
                    if isinstance(url, str) and url.startswith("data:image"):
                        yield WorkerOutput(type="image_content", content=url)

    async def _generate_stream(
            self,
            client: httpx.AsyncClient,
            url: str,
            headers: Dict[str, Any],
            payload: Dict[str, Any]
    ) -> AsyncGenerator[WorkerOutput, None]:
        """处理流式API响应，并生成 WorkerOutput 流。"""
        payload["stream"] = True
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            # **修正点**: 不立即调用 raise_for_status()，而是先检查状态码。
            # 这样我们就能在流关闭前安全地读取错误响应体。
            if not response.is_success:
                await response.aread()
                error_content = response.text
                try:
                    error_data = response.json()
                    error_content = error_data.get("error", {}).get("message", error_content)
                except json.JSONDecodeError:
                    pass
                yield WorkerOutput(type="error", content=f"API Error {response.status_code}: {error_content}")
                return

            # 状态码为 2xx，正常处理流
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)

                    if "usage" in chunk and chunk["usage"]:
                        yield WorkerOutput(type="usage", usage=chunk["usage"])

                    choices = chunk.get("choices")
                    if not (choices and len(choices) > 0):
                        continue

                    delta = choices[0].get("delta", {})
                    if not delta:
                        continue

                    reason_chunk = get_reason(delta)
                    if reason_chunk:
                        yield WorkerOutput(type="reasoning", content=reason_chunk)

                    content_chunk = delta.get("content")
                    if content_chunk:
                        yield WorkerOutput(type="content", content=content_chunk)

                    images_chunk = delta.get("images")
                    if images_chunk:
                        async for image_output in self._process_images(images_chunk):
                            yield image_output

                except json.JSONDecodeError:
                    continue

    async def _generate_non_stream(
            self,
            client: httpx.AsyncClient,
            url: str,
            headers: Dict[str, Any],
            payload: Dict[str, Any]
    ) -> AsyncGenerator[WorkerOutput, None]:
        """处理非流式API响应，并生成 WorkerOutput。"""
        payload["stream"] = False
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()  # 非流式请求在这里抛出异常是安全的
        data = response.json()

        if "usage" in data and data["usage"]:
            yield WorkerOutput(type="usage", usage=data["usage"])

        message_data = data.get("choices", [{}])[0].get("message", {})

        full_reasoning_content = get_reason(message_data)
        if full_reasoning_content:
            yield WorkerOutput(type="reasoning", content=full_reasoning_content)

        full_main_content = message_data.get("content")
        if full_main_content:
            yield WorkerOutput(type="content", content=full_main_content)

        images = message_data.get("images")
        if images:
            async for image_output in self._process_images(images):
                yield image_output

    async def generate(
            self,
            llm_input: LLMInput
    ) -> AsyncGenerator[WorkerOutput, None]:
        """
        与 OpenAI 兼容的 API 通信，解析其文本和图片响应，并生成统一的 WorkerOutput 流。
        """
        headers = {
            "Authorization": f"Bearer {llm_input.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": llm_input.model_id,
            "messages": llm_input.messages,
            **llm_input.parameters
        }
        url = f"{llm_input.api_host.rstrip('/')}/chat/completions"
        use_stream = llm_input.parameters.get('stream', True)

        try:
            async with httpx.AsyncClient(proxy=llm_input.proxy_url, timeout=llm_input.timeout) as client:
                generator = self._generate_stream(client, url, headers, payload) \
                    if use_stream else self._generate_non_stream(client, url, headers, payload)
                async for output in generator:
                    yield output

            yield WorkerOutput(type="done")

        except httpx.HTTPStatusError as e:
            # 这个异常块现在主要处理非流式请求的错误
            error_content = e.response.text
            try:
                error_data = e.response.json()
                error_content = error_data.get("error", {}).get("message", error_content)
            except json.JSONDecodeError:
                pass
            yield WorkerOutput(type="error", content=f"API Error {e.response.status_code}: {error_content}")
        except Exception as e:
            # 捕获其他类型的错误，如连接超时
            yield WorkerOutput(type="error", content=str(e))
