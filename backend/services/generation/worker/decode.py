# backend/services/generation/worker/decode.py

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessageChunk, AIMessage, ToolMessage


class BaseDecode(ABC):
    @abstractmethod
    def get_text_content(self, mode: str, message: Any) -> Optional[str]:
        pass

    @abstractmethod
    def get_reasoning_content(self, mode: str, message: Any) -> Optional[str]:
        pass

    @abstractmethod
    def get_toolcall_content(self, mode: str, message: Any) -> Optional[list]:
        pass

    @abstractmethod
    def get_toolcall_result(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_usage(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_hitl_interrupt(self, mode: str, event: Any) -> Optional[Any]:
        pass

    @abstractmethod
    def get_hitl_middleware_data(self, mode: str, event: Any) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_image_url(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        pass


class DefaultLangChainDecode(BaseDecode):
    def get_text_content(self, mode: str, message: Any) -> Optional[str]:
        return None

    def get_reasoning_content(self, mode: str, message: Any) -> Optional[str]:
        return None

    def get_image_url(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        return None

    def get_toolcall_content(self, mode: str, message: Any) -> Optional[list]:
        if mode == "updates" and isinstance(message, AIMessage):
            return getattr(message, "tool_calls", None)
        return None

    def get_toolcall_result(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(message, ToolMessage):
            return {"id": message.tool_call_id, "text": getattr(message, "text", str(message.content))}
        return None

    def get_usage(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        if isinstance(message, ToolMessage):
            return None

        if mode == "messages" and getattr(message, "usage_metadata", None):
            usage = {}
            if "input_tokens" in message.usage_metadata:
                usage["prompt_tokens"] = message.usage_metadata.get("input_tokens")
            if "output_tokens" in message.usage_metadata:
                usage["completion_tokens"] = message.usage_metadata.get("output_tokens")
            if "total_tokens" in message.usage_metadata:
                usage["total_tokens"] = message.usage_metadata.get("total_tokens")
            if "output_token_details" in message.usage_metadata:
                usage["completion_tokens_details"] = {}
                usage["completion_tokens_details"]["reasoning_tokens"] = \
                    message.usage_metadata.get("output_token_details").get("reasoning")
            return usage
        return None

    def get_hitl_interrupt(self, mode: str, event: Any) -> Optional[Any]:
        if mode == "updates" and isinstance(event, dict) and "__interrupt__" in event:
            return event["__interrupt__"][0].value
        return None

    def get_hitl_middleware_data(self, mode: str, event: Any) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(event, dict) and "HumanInTheLoopMiddleware.after_model" in event:
            data = event["HumanInTheLoopMiddleware.after_model"]
            if not data:
                return None

            messages = data.get("messages", [])
            rejected_results = []
            rejected_ids = set()

            for msg in messages:
                if isinstance(msg, ToolMessage):
                    rejected_ids.add(msg.tool_call_id)
                    rejected_results.append({
                        "id": msg.tool_call_id,
                        "name": getattr(msg, "name", ""),
                        "content": msg.content
                    })

            approved_calls = []
            for msg in messages:
                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                    for call in msg.tool_calls:
                        if call.get("id") not in rejected_ids:
                            approved_calls.append(call)

            return {"approved_calls": approved_calls, "rejected_results": rejected_results}
        return None


class OpenAiDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.content
        return None

    def get_reasoning_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
        return None

    def get_image_url(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(message, AIMessage):
            if "images" in message.additional_kwargs:
                for image in message.additional_kwargs["images"]:
                    return image
        return None


class AnthropicDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            if hasattr(message, "content_blocks"):
                for sub_message in message.content_blocks:
                    if sub_message.get("type", "") == "text":
                        return sub_message.get("text", "")
        return None

    def get_reasoning_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            if hasattr(message, "content_blocks"):
                for sub_message in message.content_blocks:
                    if sub_message.get("type", "") == "reasoning":
                        return sub_message.get("reasoning", "")
        return None

    def get_image_url(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        return None


class GoogleDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            if hasattr(message, "content_blocks"):
                return "\n".join([subm.get("text", "") for subm in message.content_blocks if subm.get("type", "") == 'text'])
        return None

    def get_reasoning_content(self, mode: str, message: Any) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            reasoning = message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
            if reasoning:
                return reasoning
            if hasattr(message, "content_blocks"):
                return "".join([sub.get("reasoning", "") for sub in message.content_blocks if sub.get("type", "") == "reasoning"])
        return None

    def get_image_url(self, mode: str, message: Any) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(message, AIMessage):
            if "images" in message.additional_kwargs:
                for image in message.additional_kwargs["images"]:
                    return image
        return None


class DecoderRegistry:
    _decoders: Dict[str, BaseDecode] = {
        "openai": OpenAiDecode(),
        "anthropic": AnthropicDecode(),
        "google_genai": GoogleDecode(),
        "deepseek": OpenAiDecode(),
        "default": DefaultLangChainDecode()
    }

    @classmethod
    def get_decoder(cls, model_provider: str) -> BaseDecode:
        provider_key = (model_provider or "").lower()
        return cls._decoders.get(provider_key, cls._decoders["default"])
