# backend/services/generation/openai_worker.py
import httpx
import json
import traceback
from typing import AsyncGenerator, Dict, Any, List

from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.llm_io import LLMInput, WorkerOutput


def get_reason(delta: dict) -> str:
    """从响应块中安全地提取 'reasoning' 内容。"""
    return delta.get("reasoning_content") or delta.get("reasoning")


class OpenAIGenerateWorker(AbstractGenerateWorker):
    """
    OpenAI 生成工作者，负责与 OpenAI 兼容的 API 交互。
    能够处理文本、图片和工具调用等多模态内容的输入与输出，并生成标准化的 WorkerOutput 流。
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
            payload: Dict[str, Any],
            timeout: int
    ) -> AsyncGenerator[WorkerOutput, None]:
        """处理流式API响应，并生成 WorkerOutput 流。"""
        payload["stream"] = True

        # 工具调用缓冲池，用于拼接流式传输的片段
        # Key: index (int), Value: Dict (构建中的 tool_call 对象)
        tool_calls_buffer = {}

        async with client.stream("POST", url, headers=headers, json=payload, timeout=timeout) as response:
            if not response.is_success:
                await response.aread()
                error_content = response.text
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        error_content = json.dumps(error_data, indent=4, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
                yield WorkerOutput(type="error", content=f"\nAPI Error {response.status_code}:\n ```\n{error_content}\n```")
                return

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

                    choice = choices[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason")

                    # 1. 处理工具调用片段
                    tool_calls_chunks = delta.get("tool_calls")
                    if tool_calls_chunks:
                        for tc_chunk in tool_calls_chunks:
                            # 兼容处理：如果块内没有 index，则默认为 0。
                            # 这能兼容那些只流式传输单个工具调用且不提供 index 的模型。
                            index = tc_chunk.get("index", 0)

                            if index not in tool_calls_buffer:
                                tool_calls_buffer[index] = {
                                    "index": index,
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }

                            current_buffer = tool_calls_buffer[index]
                            if tc_chunk.get("id"):
                                current_buffer["id"] = tc_chunk["id"]

                            if tc_chunk.get("function"):
                                fn_chunk = tc_chunk["function"]
                                if fn_chunk.get("name"):
                                    current_buffer["function"]["name"] += fn_chunk["name"]
                                if fn_chunk.get("arguments"):
                                    current_buffer["function"]["arguments"] += fn_chunk["arguments"]

                    # 2. 处理常规内容
                    if not tool_calls_chunks:
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

                    # 3. 检查是否因工具调用结束
                    if finish_reason == "tool_calls" or (finish_reason and tool_calls_buffer):
                        if tool_calls_buffer:
                            # 将 buffer 转换为列表并排序
                            final_tool_calls = sorted(tool_calls_buffer.values(), key=lambda x: x["index"])
                            yield WorkerOutput(type="tool_call", tool_calls=final_tool_calls)
                            tool_calls_buffer = {}

                except json.JSONDecodeError:
                    print(f"Warning: Could not decode JSON from stream line: {data_str}")
                    continue
                except IndexError as e:
                    print(f"IndexError: {traceback.format_exc()},data_str: {data_str}")
                    raise e

            # 流结束后的兜底检查：如果 buffer 中还有数据（例如异常中断），尝试输出
            if tool_calls_buffer:
                final_tool_calls = sorted(tool_calls_buffer.values(), key=lambda x: x["index"])
                yield WorkerOutput(type="tool_call", tool_calls=final_tool_calls)

    async def _generate_non_stream(
            self,
            client: httpx.AsyncClient,
            url: str,
            headers: Dict[str, Any],
            payload: Dict[str, Any],
            timeout: int
    ) -> AsyncGenerator[WorkerOutput, None]:
        """处理非流式API响应，并生成 WorkerOutput。"""
        payload["stream"] = False
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        if "usage" in data and data["usage"]:
            yield WorkerOutput(type="usage", usage=data["usage"])


        if not data.get("choices", [{}]):
            print(data)
        choice = data.get("choices", [{}])[0]

        message_data = choice.get("message", {})

        # 处理工具调用
        tool_calls = message_data.get("tool_calls")
        if tool_calls:
            yield WorkerOutput(type="tool_call", tool_calls=tool_calls)

        # 处理常规内容
        full_reasoning_content = get_reason(message_data)
        if full_reasoning_content:
            yield WorkerOutput(type="reasoning", content=full_reasoning_content)

        # content 和 tool_calls 通常是互斥的
        if not tool_calls:
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
        与 OpenAI 兼容的 API 通信，解析其文本、图片和工具调用响应，并生成统一的 WorkerOutput 流。
        """
        headers = {
            "Authorization": f"Bearer {llm_input.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/RAmenLch/mambochat",
            "X-Title": "MamboChat",
        }
        payload = {
            "model": llm_input.model_id,
            "messages": llm_input.messages,
            **llm_input.parameters
        }

        # 注入工具定义
        if llm_input.tools:
            payload["tools"] = llm_input.tools
        if llm_input.tool_choice:
            payload["tool_choice"] = llm_input.tool_choice

        url = f"{llm_input.api_host.rstrip('/')}/chat/completions"
        use_stream = llm_input.parameters.get('stream', True)

        try:
            async with httpx.AsyncClient(proxy=llm_input.proxy_url) as client:
                generator = self._generate_stream(client, url, headers, payload, llm_input.timeout) \
                    if use_stream else self._generate_non_stream(client, url, headers, payload, llm_input.timeout)
                async for output in generator:
                    yield output

            yield WorkerOutput(type="done")

        except httpx.HTTPStatusError as e:
            error_content = e.response.text
            try:
                error_data = e.response.json()
                if isinstance(error_data, dict):
                    error_content = error_data.get("error", {}).get("message", error_content)
            except json.JSONDecodeError:
                pass
            yield WorkerOutput(type="error", content=f"API Error {e.response.status_code}: {error_content}")
        except Exception as e:
            print(f"[OpenAIGenerateWorker] Caught unexpected exception:")
            traceback.print_exc()
            yield WorkerOutput(type="error", content=f"An unexpected error occurred: {str(e)}")
