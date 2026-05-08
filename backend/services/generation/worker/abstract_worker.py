import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any, Dict, List, Tuple, Union

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import BaseDecode, DecoderRegistry
from services.generation.core.llm_io import SummarizationEventInfo

StreamEvent = Union[ToolMessage, AIMessageChunk, AIMessage, Dict[str, Any],SummarizationEventInfo]


class AbstractGenerateWorker(ABC):

    def resolve_decoder(self, message: StreamEvent) -> BaseDecode:
        provider = "default"
        if isinstance(message, BaseMessage) and isinstance(message.response_metadata, dict):
            provider = message.response_metadata.get("model_provider", "default")
        return DecoderRegistry.get_decoder(provider)

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        lc_messages = []
        for msg in messages:
            id = msg.get("id")
            role = msg.get("role")
            content = msg.get("content", "") or ''
            name = msg.get("name")

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(id = id,content=content, name=name))
            elif role == "assistant":
                raw_tool_calls = msg.get("tool_calls")
                lc_tool_calls = []

                additional_kwargs = {}
                reasoning_content = msg.get("reasoning_content")
                if reasoning_content:
                    additional_kwargs["reasoning_content"] = reasoning_content

                if raw_tool_calls and isinstance(raw_tool_calls, list):
                    for tc in raw_tool_calls:
                        if "function" in tc:
                            try:
                                args_str = tc["function"].get("arguments", "{}")
                                args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
                            except json.JSONDecodeError:
                                args_dict = {}

                            lc_tool_calls.append({
                                "name": tc["function"].get("name", ""),
                                "args": args_dict,
                                "id": tc.get("id", "")
                            })
                        elif "name" in tc and "args" in tc:
                            lc_tool_calls.append({
                                "name": tc.get("name", ""),
                                "args": tc.get("args", {}),
                                "id": tc.get("id", "")
                            })

                if lc_tool_calls:
                    lc_messages.append(AIMessage(id = id,content=content, name=name, tool_calls=lc_tool_calls, additional_kwargs=additional_kwargs))
                else:
                    lc_messages.append(AIMessage(id = id,content=content, name=name, additional_kwargs=additional_kwargs))

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    lc_messages.append(ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name=name
                    ))
            else:
                lc_messages.append(HumanMessage(id = id,content=content, name=name))

        return lc_messages

    @abstractmethod
    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[Tuple[str, StreamEvent], None]:
        if False:
            yield
