from typing import Any, Dict, Optional, Type, Union

import openai
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class ExtendedChatOpenAI(ChatOpenAI):
    """
    增强版 ChatOpenAI。

    功能：
    1. 流式 (Stream): 捕获 delta 中的 reasoning_content, images 等非标准字段。
    2. 非流式 (Invoke): 捕获 message 中的 reasoning_content, images 等非标准字段。
    """

    # --- 1. 处理流式模式 (stream=True) ---
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: Dict[str, Any],
        default_chunk_class: Type,
        base_generation_info: Optional[Dict],
    ) -> Optional[ChatGenerationChunk]:
        # 调用父类逻辑获取基础 chunk
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )

        if generation_chunk is None:
            return None

        # 提取 delta 中的额外字段
        choices = chunk.get("choices", [])
        if not choices:
            return generation_chunk

        delta = choices[0].get("delta", {})

        # 定义需要捕获的非标准字段
        extra_fields = ["reasoning_content", "reasoning", "images"]

        for field in extra_fields:
            if val := delta.get(field):
                # 注入到 additional_kwargs
                generation_chunk.message.additional_kwargs[field] = val

        return generation_chunk

    # --- 2. 处理非流式模式 (stream=False) ---
    def _create_chat_result(
        self,
        response: Union[Dict[str, Any], openai.BaseModel],
        generation_info: Optional[Dict] = None,
    ) -> ChatResult:
        # 1. 调用父类方法，生成标准的 ChatResult
        # 父类内部调用了 _convert_dict_to_message，此时非标准字段已经被丢弃了
        chat_result = super()._create_chat_result(response, generation_info)

        # 2. 获取原始响应字典
        if isinstance(response, openai.BaseModel):
            response_dict = response.model_dump()
        else:
            response_dict = response

        # 3. 重新遍历原始响应，把丢弃的字段找回来，塞进 additional_kwargs
        choices = response_dict.get("choices", [])

        # 这里的 generations 和 choices 是一一对应的 (通常 n=1)
        for gen, choice in zip(chat_result.generations, choices):
            message_dict = choice.get("message", {})

            # 定义需要捕获的非标准字段
            extra_fields = ["reasoning_content", "reasoning", "images"]

            for field in extra_fields:
                if val := message_dict.get(field):
                    # 这里的 gen.message 是一个 AIMessage 对象
                    gen.message.additional_kwargs[field] = val

        return chat_result


