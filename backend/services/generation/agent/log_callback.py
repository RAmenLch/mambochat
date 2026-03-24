from typing import Any, Callable, Dict, List
import json

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AnyMessage
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langgraph.config import get_config

from backend.services.generation.core.llm_io import RunTimeConfig


# ==========================================
# 1. 定义一个专门用来拦截底层报文的 Callback
# ==========================================
class RawPayloadLoggingCallback(AsyncCallbackHandler):
    def __init__(self, config: RunTimeConfig):
        self.chat_id = config.message_id
        self.message_id = config.message_id
        self.manager_name = config.message_id

    async def on_chat_model_start(
            self,
            serialized: Dict[str, Any],
            messages: List[List[BaseMessage]],
            **kwargs: Any,
    ) -> None:

        """
        这个钩子会在底层 ChatModel 准备调用 OpenAI/Anthropic SDK 的前一刻触发！
        """
        # kwargs["invocation_params"] 包含了即将发送给 API 的核心参数
        # 包括：model, temperature, max_tokens, tools (已经被转换成了 JSON Schema) 等
        invocation_params = kwargs.get("invocation_params", {})

        # 将 LangChain 的 Message 对象转换为普通的字典列表 (类似 OpenAI API 格式)
        # 注意：messages 是一个二维数组，通常取 [0] 即可
        raw_messages = [msg.model_dump() for msg in messages[0]] if messages else []

        # 组装一个最接近真实 HTTP Payload 的大字典
        raw_payload = {
            "messages": raw_messages,
            **invocation_params  # 展开其他所有参数 (如 tools, tool_choice 等)
        }
        config = get_config().get("metadata")
        print(config)
        # 打印或写入你的日志系统，完美绑定了 message_id！
        print(f"\n{'='*20} 🛫 [HTTP Payload | MsgID: {self.message_id}] {'='*20}")
        # 使用 json.dumps 打印出漂亮的 JSON 格式
        print(json.dumps(raw_payload, indent=2, ensure_ascii=False))
        print("=" * 65 + "\n")