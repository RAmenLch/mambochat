from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
)
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.utils import from_env, secret_from_env
from langchain_openai import ChatOpenAI
from pydantic import Field, SecretStr, ConfigDict


class ChatDeepSeek(ChatOpenAI):
    """
    自定义 DeepSeek Chat 模型（支持 V4）。
    功能说明：
    1. 思考模式(Reasoning)下工具调用(Tool Call)时，回传 reasoning_content。
    2. 支持 DeepSeek V4 的 thinking 参数和 reasoning_effort 参数。
       - thinking: {"type": "enabled"/"disabled"} 控制思考模式开关
       - reasoning_effort: "high"/"max" 控制思考强度
    3. 不对 tool/assistant 消息的 content 做扁平化：DeepSeek 现版本已接受 list content
       （含纯文本块与 image_url 图片块，实测通过），扁平化会剥离 tool 消息中的
       image_url 块，导致 vision 模型（deepseek-v4-flash-vision-exp）无法识图。
    """

    # 默认配置
    deepseek_api_base: str = Field(
        default_factory=from_env("DEEPSEEK_API_BASE", default="https://api.deepseek.com"),
        alias="base_url"
    )
    deepseek_api_key: SecretStr = Field(
        default_factory=secret_from_env("DEEPSEEK_API_KEY", default=None),
        alias="api_key"
    )
    model_name: str = Field(default="deepseek-v4-pro", alias="model")

    # DeepSeek V4 思考模式参数
    thinking: Optional[Dict[str, str]] = Field(
        default=None,
        description='DeepSeek V4 思考模式开关，格式：{"type": "enabled"} 或 {"type": "disabled"}。'
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description='DeepSeek V4 推理强度："high" 或 "max"。'
    )

    model_config = ConfigDict(populate_by_name=True)

    @property
    def _llm_type(self) -> str:
        return "deepseek-chat-custom"

    def _get_request_payload(
            self,
            input_: List[BaseMessage],
            *args,
            **kwargs
    ) -> Dict:
        """
        重写构建请求体的方法。
        """
        # 1. 获取 OpenAI 格式的标准 payload
        payload = super()._get_request_payload(input_, *args, **kwargs)

        # 2. 注入 DeepSeek V4 思考模式参数
        # reasoning_effort 是 OpenAI SDK 支持的标准参数（o1/o3 系列也使用）
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        # thinking 是 DeepSeek 扩展参数，必须通过 extra_body 传递，不能直接放在请求体中
        if self.thinking is not None:
            extra_body = payload.get("extra_body", {}) or {}
            extra_body.update({"thinking": self.thinking})
            payload["extra_body"] = extra_body

        # 3. 思考模式与 tool_choice 互斥处理
        # deepseek 思考模式下，tool_choice 指定具体函数名
        # （如 {"type": "function", "function": {"name": "SecurityReviewResult"}}）
        # 会触发 400 报错 "Thinking mode does not support this tool_choice"。
        # 此处在请求体层面自动关闭思考，保证 structured output / 安全审核等场景正常工作。
        tool_choice = payload.get("tool_choice")
        if tool_choice and not isinstance(tool_choice, str):
            extra_body = payload.get("extra_body", {}) or {}
            thinking_cfg = extra_body.get("thinking")
            # thinking_cfg 为 None 时 deepseek 默认开启思考，同样需要显式关闭
            is_thinking_on = thinking_cfg is None or thinking_cfg.get("type") == "enabled"
            if is_thinking_on:
                extra_body["thinking"] = {"type": "disabled"}
                payload["extra_body"] = extra_body

        # 4. 遍历 payload 中的消息进行修复
        for i, payload_msg in enumerate(payload["messages"]):

            # --- 修复: 回传 reasoning_content (解决 400 错误) ---
            # 找到对应的 LangChain 原始消息
            if i < len(input_):
                lc_msg = input_[i]
                if isinstance(lc_msg, AIMessage):
                    # 检查 additional_kwargs 中是否有 reasoning_content
                    reasoning = lc_msg.additional_kwargs.get("reasoning_content")
                    if reasoning:
                        # 显式将 reasoning_content 加回发送给 API 的字典中
                        payload_msg["reasoning_content"] = reasoning

        return payload

    def _create_chat_result(
            self, response: Union[Dict, Any], generation_info: Optional[Dict] = None
    ) -> ChatResult:
        """
        处理非流式响应：从 API 响应中提取 reasoning_content 并存入 additional_kwargs。
        """
        rtn = super()._create_chat_result(response, generation_info)

        # 尝试从 response 中提取 reasoning_content
        choices = getattr(response, "choices", [])
        if not choices and isinstance(response, dict):
            choices = response.get("choices", [])

        if choices:
            choice = choices[0]
            message = getattr(choice, "message", None) or choice.get("message", {})

            # 获取 reasoning_content
            reasoning_content = None
            if hasattr(message, "reasoning_content"):
                reasoning_content = message.reasoning_content
            elif isinstance(message, dict):
                reasoning_content = message.get("reasoning_content")

            # 如果存在，存入 additional_kwargs
            if reasoning_content:
                rtn.generations[0].message.additional_kwargs["reasoning_content"] = reasoning_content

        return rtn

    def _convert_chunk_to_generation_chunk(
            self,
            chunk: Dict,
            default_chunk_class: Any,
            base_generation_info: Optional[Dict]
    ) -> Optional[ChatGenerationChunk]:
        """
        处理流式响应：从 Chunk 中提取 reasoning_content 的增量。
        """
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )

        if not generation_chunk:
            return None

        # 尝试从 chunk delta 中提取 reasoning_content
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            reasoning_content = delta.get("reasoning_content")

            if reasoning_content:
                # 将 reasoning_content 放入 additional_kwargs
                generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content

        return generation_chunk
