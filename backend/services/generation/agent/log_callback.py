# backend/services/generation/agent/log_callback.py

import asyncio
from typing import Any, Dict, List
import json

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langgraph.config import get_config

from backend.services.generation.core.llm_io import RunTimeConfig
from backend.services.log_service import async_save_post_log


# ==========================================
# 1. 定义一个专门用来拦截底层报文的 Callback
# ==========================================
class RawPayloadLoggingCallback(AsyncCallbackHandler):
    def __init__(self, config: RunTimeConfig):
        # 修复了原代码中全部映射为 message_id 的 bug
        self.chat_id = config.chat_id
        self.message_id = config.message_id
        self.manager_name = config.manager_name

    async def on_chat_model_start(
            self,
            serialized: Dict[str, Any],
            messages: List[List[BaseMessage]],
            **kwargs: Any,
    ) -> None:
        """
        这个钩子会在底层 ChatModel 准备调用 SDK 的前一刻触发
        """
        # kwargs["invocation_params"] 包含了即将发送给 API 的核心参数
        invocation_params = kwargs.get("invocation_params", {})

        # 将 LangChain 的 Message 对象转换为普通的字典列表
        raw_messages = [msg.model_dump() for msg in messages[0]] if messages else []

        # 组装一个最接近真实 HTTP Payload 的大字典
        raw_payload = {
            "messages": raw_messages,
            **invocation_params
        }

        # 安全获取 LangGraph 运行时的 metadata
        try:
            meta_data = get_config().get("metadata", {})
        except Exception:
            meta_data = {}

        # 提取 agent_name
        agent_name = meta_data.get("lc_agent_name")

        # 触发后台异步保存任务 (Fire-and-Forget)
        # 脱离当前 LangGraph 的执行阻塞，直接交由 asyncio 事件循环调度
        asyncio.create_task(
            async_save_post_log(
                chat_id=self.chat_id,
                message_id=self.message_id,
                manager_name=self.manager_name,
                agent_name=agent_name,
                config_meta_data=meta_data,
                raw_payload=raw_payload
            )
        )
