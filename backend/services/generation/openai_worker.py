# backend/services/generation/openai_worker.py
import httpx
import json
from typing import AsyncGenerator, Dict, Any

from .base import AbstractGenerateWorker
from .llm_io import LLMInput, WorkerOutput


def get_reason(delta: dict) -> str:
    return delta.get("reasoning_content") or delta.get("reasoning")


class OpenAIGenerateWorker(AbstractGenerateWorker):
    """
    OpenAI 生成工作者，负责与 OpenAI 兼容的 API 交互并生成标准化的 WorkerOutput 流。
    能够根据传入的 LLMInput，自动选择流式或非流式模式进行通信。
    """

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
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices")
                    if not (choices and len(choices) > 0):
                        continue

                    delta = choices[0].get("delta", {})

                    reason_chunk = get_reason(delta)
                    if reason_chunk:
                        yield WorkerOutput(type="reasoning", content=reason_chunk)

                    content_chunk = delta.get("content")
                    if content_chunk:
                        yield WorkerOutput(type="content", content=content_chunk)
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
        response.raise_for_status()
        data = response.json()

        message_data = data.get("choices", [{}])[0].get("message", {})
        full_reasoning_content = get_reason(message_data)
        full_main_content = message_data.get("content")

        if full_reasoning_content:
            yield WorkerOutput(type="reasoning", content=full_reasoning_content)
        if full_main_content:
            yield WorkerOutput(type="content", content=full_main_content)

    async def generate(
        self,
        llm_input: LLMInput
    ) -> AsyncGenerator[WorkerOutput, None]:
        """
        与 OpenAI API 通信，解析响应，并生成统一的 WorkerOutput 流。
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

        except Exception as e:
            yield WorkerOutput(type="error", content=str(e))

