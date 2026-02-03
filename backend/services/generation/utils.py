from langchain_core.messages import AIMessageChunk,AIMessage, ToolMessage

class OpenAiDecode:
    @staticmethod
    def get_text_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message,AIMessage):
            return message.content
        else:
            return None

    @staticmethod
    def get_reasoning_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates":
            return None
        if mode == "messages" and isinstance(message,AIMessage):
            return message.additional_kwargs.get("reasoning") or message.additional_kwargs.get("reasoning_content")
        else:
            return None

    @staticmethod
    def get_toolcall_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates" and isinstance(message,AIMessage):
            return message.tool_calls # 示例 [{'name': 'ddgs_search', 'args': {'query': '今日广州天气', 'max_results': 5}, 'id': '019bcccc33c40a0867a2879848bddca0', 'type': 'tool_call'}]
        else:
            return None

    @staticmethod
    def get_toolcall_result(mode,message:ToolMessage):
        if mode == "updates" and isinstance(message,ToolMessage):
            return {"id": message.tool_call_id, "text": message.text} # text 工具调用mcp方法返回的json
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



class AnthropicDecode:
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
    def get_toolcall_content(mode,message:AIMessageChunk| AIMessage):
        if mode == "updates" and isinstance(message,AIMessage):
            return message.tool_calls # 示例 [{'name': 'ddgs_search', 'args': {'query': '今日广州天气', 'max_results': 5}, 'id': '019bcccc33c40a0867a2879848bddca0', 'type': 'tool_call'}]
        else:
            return None