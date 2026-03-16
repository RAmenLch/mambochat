from langchain_core.messages import AIMessageChunk,AIMessage, ToolMessage

# backend/services/generation/worker/decode.py

from langchain_core.messages import AIMessageChunk, AIMessage, ToolMessage

class BaseDecode:
    @staticmethod
    def get_text_content(mode, message):
        pass

    @staticmethod
    def get_reasoning_content(mode, message):
        pass

    @staticmethod
    def get_toolcall_content(mode, message: AIMessageChunk | AIMessage):
        if mode == "updates" and isinstance(message, AIMessage):
            return message.tool_calls
        else:
            return None

    @staticmethod
    def get_toolcall_result(mode, message: ToolMessage):
        if mode == "updates" and isinstance(message, ToolMessage):
            return {"id": message.tool_call_id, "text": message.text}
        else:
            return None

    @staticmethod
    def get_usage(mode, message: AIMessage):
        if isinstance(message, ToolMessage):
            return None

        if (mode == "messages" and message.usage_metadata):
            usage = {}
            if "input_tokens" in message.usage_metadata:
                usage["prompt_tokens"] = message.usage_metadata.get("input_tokens")
            if "output_tokens" in message.usage_metadata:
                usage["completion_tokens"] = message.usage_metadata.get("output_tokens")
            if "total_tokens" in message.usage_metadata:
                usage["total_tokens"] = message.usage_metadata.get("total_tokens")
            if "output_token_details" in message.usage_metadata:
                usage["completion_tokens_details"] = {}
                usage["completion_tokens_details"]["reasoning_tokens"] \
                    = message.usage_metadata.get("output_token_details").get("reasoning")
            return usage
        else:
            return None

    @staticmethod
    def get_hitl_interrupt(mode, event):
        if mode == "updates" and isinstance(event, dict) and "__interrupt__" in event:
            return event["__interrupt__"][0].value
        return None

    @staticmethod
    def get_hitl_middleware_data(mode, event):
        if mode == "updates" and isinstance(event, dict) and "HumanInTheLoopMiddleware.after_model" in event:
            data = event["HumanInTheLoopMiddleware.after_model"]
            if not data:
                return None

            messages = data.get("messages", [])
            rejected_results = []
            rejected_ids = set()

            # 1. 第一遍遍历：收集所有被中间件拦截/拒绝的工具调用
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    rejected_ids.add(msg.tool_call_id)
                    rejected_results.append({
                        "id": msg.tool_call_id,
                        "name": msg.name,
                        "content": msg.content
                    })

            # 2. 第二遍遍历：提取真正被批准的工具调用（过滤掉已被拒绝的）
            approved_calls = []
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for call in msg.tool_calls:
                        if call.get("id") not in rejected_ids:
                            approved_calls.append(call)

            return {"approved_calls": approved_calls, "rejected_results": rejected_results}
        return None


class OpenAiDecode(BaseDecode):
    @staticmethod
    def get_text_content(mode, message: AIMessageChunk | AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.content
        else:
            return None

    @staticmethod
    def get_reasoning_content(mode, message: AIMessageChunk | AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
        else:
            return None

    @staticmethod
    def get_image_url(mode, message: AIMessageChunk | AIMessage):
        if mode == "updates" and isinstance(message, AIMessage):
            if "images" in message.additional_kwargs:
                for image in message.additional_kwargs["images"]:
                    return image
                else:
                    return None
            else:
                return None
        else:
            return None


class AnthropicDecode(BaseDecode):
    @staticmethod
    def get_text_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message,AIMessage):
            for sub_message in message.content_blocks:
                if sub_message.get("type","") == "text":
                    return sub_message.get("text","")
            else:
                return None
        else:
            return None

    @staticmethod
    def get_reasoning_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message,AIMessage):
            for sub_message in message.content_blocks:
                if sub_message.get("type","") == "reasoning":
                    return sub_message.get("reasoning","")
            else:
                return None
        else:
            return None

    @staticmethod
    def get_image_url(mode,message:AIMessageChunk| AIMessage):
        return None



class GoogleDecode(BaseDecode):
    @staticmethod
    def get_text_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message,AIMessage):
            return "\n".join([subm.get("text","") for subm in message.content_blocks if subm.get("type","") == 'text'])
        else:
            return None

    @staticmethod
    def get_reasoning_content(mode,message):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message, AIMessage):
            return message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content") \
                   or "".join([sub.get("reasoning","") for sub in message.content_blocks if sub.get("type","") == "reasoning"])
        else:
            return None

    @staticmethod
    def get_image_url(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates" and isinstance(message,AIMessage):
            if "images" in message.additional_kwargs:
                for image in message.additional_kwargs["images"]:
                    return image # {"image_url":{"url":"data:image..."}}
                else:
                    return None
            else:
                return None
        else:
            return None