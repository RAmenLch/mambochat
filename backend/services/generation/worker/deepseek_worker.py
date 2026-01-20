import json
from typing import List, Dict, Any

from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage, BaseMessage

from backend.services.generation.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from backend.services.generation.worker.deepseek_chat_model import ChatDeepSeek


class DeepSeekWorker(ChatWorker):
    """
    DeepSeek 生成工作者。
    继承自 ChatWorker，针对 DeepSeek 的思考模式（Reasoning Mode）进行了适配。
    """

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        """
        将 LLMInput 中的字典格式消息转换为 LangChain 的 Message 对象。
        """
        lc_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            name = msg.get("name")

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content, name=name))
            elif role == "assistant":
                additional_kwargs = {}

                # 1. 恢复 tool_calls 并进行格式转换
                raw_tool_calls = msg.get("tool_calls", [])
                lc_tool_calls = []

                for rtc in raw_tool_calls:
                    # 检查是否为 OpenAI 原生格式 (包含 'function' 字段)
                    if "function" in rtc:
                        try:
                            # 解析 arguments 字符串为字典
                            args_str = rtc["function"].get("arguments", "{}")
                            # 容错处理：有时候 arguments 已经是 dict 了
                            if isinstance(args_str, dict):
                                args = args_str
                            else:
                                args = json.loads(args_str)

                            lc_tool_calls.append({
                                "name": rtc["function"]["name"],
                                "args": args,
                                "id": rtc["id"],
                                "type": "tool_call"
                            })
                        except Exception as e:
                            print(f"Error parsing tool call args: {e}")
                            # 如果解析失败，保留原始数据防止丢失，虽然可能会报错
                            lc_tool_calls.append(rtc)
                    else:
                        # 如果已经是 LangChain 格式，直接添加
                        lc_tool_calls.append(rtc)

                # 2. 故意不提取 reasoning_content (Turn 2+ 节省 Token)
                # 如果你需要同一轮内的 reasoning，可以在这里加回判断逻辑

                lc_messages.append(AIMessage(
                    content=content,
                    name=name,
                    additional_kwargs=additional_kwargs,
                    tool_calls=lc_tool_calls  # <--- 传入转换后的 tool_calls
                ))

            elif role == "tool":
                # ToolMessage 需要 tool_call_id
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    lc_messages.append(ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name=name
                    ))
            else:
                lc_messages.append(HumanMessage(content=content, name=name))

        return lc_messages

    def _create_model(self, llm_input: LLMInput) -> ChatDeepSeek:
        """
        根据 LLMInput 配置创建自定义的 ChatDeepSeek 实例。
        使用自定义的 ChatDeepSeek 类以修复工具调用时的 payload 构建问题。
        """
        model_kwargs = llm_input.parameters.copy()
        stream = model_kwargs.pop("stream", True)

        openai_proxy = llm_input.proxy_url if llm_input.proxy_url else None

        return ChatDeepSeek(
            model=llm_input.model_id,
            api_key=llm_input.api_key,
            base_url=llm_input.api_host.rstrip("/"),
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.timeout,
            streaming=stream
        )
