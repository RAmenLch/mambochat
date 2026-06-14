# backend/services/generation/worker/decode.py

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class BaseDecode(ABC):
    @abstractmethod
    def get_text_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        pass

    @abstractmethod
    def get_reasoning_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        pass

    @abstractmethod
    def get_toolcall_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[list]:
        pass

    @abstractmethod
    def get_toolcall_result(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_usage(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_hitl_interrupt(self, mode: str, event: Union[BaseMessage, Dict[str, Any]]) -> Optional[Any]:
        pass

    @abstractmethod
    def get_hitl_middleware_data(self, mode: str, event: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_image_url(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        pass


class DefaultLangChainDecode(BaseDecode):
    def get_text_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        return None

    def get_reasoning_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        return None

    def get_image_url(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return None

    def get_toolcall_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[list]:
        if mode == "updates" and isinstance(message, AIMessage):
            return message.tool_calls or None
        return None

    def get_toolcall_result(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(message, ToolMessage):
            return {"id": message.tool_call_id, "text": str(message.text)}
        return None

    def get_usage(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(message, AIMessage):
            return None

        if mode == "messages" and message.usage_metadata:
            usage: Dict[str, Any] = {}
            metadata: Dict[str, Any] = dict(message.usage_metadata)

            if "input_tokens" in metadata:
                usage["prompt_tokens"] = metadata["input_tokens"]
            if "output_tokens" in metadata:
                usage["completion_tokens"] = metadata["output_tokens"]
            if "total_tokens" in metadata:
                usage["total_tokens"] = metadata["total_tokens"]

            if "output_token_details" in metadata:
                reasoning = (metadata.get("output_token_details") or {}).get("reasoning")
                if reasoning is not None:
                    usage["completion_tokens_details"] = {"reasoning_tokens": reasoning}

            # 缓存命中 = input_token_details.cache_read (LangChain 已统一提取)
            input_details = dict(metadata.get("input_token_details") or {})
            cache_read = input_details.get("cache_read")
            if isinstance(cache_read, int) and cache_read > 0:
                prompt_total = usage.get("prompt_tokens", 0) or 0
                usage["cache_hit_tokens"] = cache_read
                usage["cache_miss_tokens"] = max(prompt_total - cache_read, 0)

            return usage
        return None

    def get_hitl_interrupt(self, mode: str, event: Union[BaseMessage, Dict[str, Any]]) -> Optional[Any]:
        if mode == "updates" and isinstance(event, dict) and "__interrupt__" in event:
            return event["__interrupt__"][0].value
        return None

    def get_hitl_middleware_data(self, mode: str, event: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(event, dict):
            data = event.get("HumanInTheLoopMiddleware.after_model") or event.get("AutoSecurityReviewMiddleware.after_model")
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
                        "name": msg.name or "",
                        "content": msg.content
                    })

            approved_calls = []
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for call in msg.tool_calls:
                        if call.get("id") not in rejected_ids:
                            approved_calls.append(call)

            return {"approved_calls": approved_calls, "rejected_results": rejected_results}
        return None


class OpenAiDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.content
        return None

    def get_reasoning_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
        return None

    def get_image_url(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if mode == "updates" and isinstance(message, AIMessage):
            if "images" in message.additional_kwargs:
                for image in message.additional_kwargs["images"]:
                    return image
        return None


class AnthropicDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            for sub_message in message.content_blocks:
                if sub_message.get("type", "") == "text":
                    return sub_message.get("text", "")
        return None

    def get_reasoning_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            for sub_message in message.content_blocks:
                if sub_message.get("type", "") == "reasoning":
                    return sub_message.get("reasoning", "")
        return None

    def get_image_url(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return None


class GoogleDecode(DefaultLangChainDecode):
    def get_text_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return "\n".join([subm.get("text", "") for subm in message.content_blocks if subm.get("type", "") == 'text'])
        return None

    def get_reasoning_content(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[str]:
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            reasoning = message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
            if reasoning:
                return reasoning
            return "".join([sub.get("reasoning", "") for sub in message.content_blocks if sub.get("type", "") == "reasoning"])
        return None

    def get_image_url(self, mode: str, message: Union[BaseMessage, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
