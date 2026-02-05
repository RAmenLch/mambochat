from typing import List, Dict, Any

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage

from backend.services.generation.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from langchain_anthropic import ChatAnthropic

from backend.services.generation.worker.decode import BaseDecode, AnthropicDecode


class AnthropicWorker(ChatWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ExtendedChatOpenAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """
    @staticmethod
    def get_decode() -> type[BaseDecode]:
        return AnthropicDecode


    def _exchange_image_message(self,content:Any):
        if isinstance(content,list):
            inner_content = []
            for subm in content:
                if subm.get("type","") == "image_url":
                    image_data = subm.get("image_url",{}).get("url","").split(";")
                    if len(image_data) < 2:
                        continue
                    else:
                        imageA = {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_data[0][5:],
                                "data":image_data[1][7:]
                            }
                        }
                        inner_content.append(imageA)
                else: inner_content.append(subm)
            return inner_content
        else:
            return content


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
                lc_messages.append(HumanMessage(content=self._exchange_image_message(content), name=name))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=self._exchange_image_message(content), name=name))
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
                # 默认当作 HumanMessage 处理
                lc_messages.append(HumanMessage(content=self._exchange_image_message(content), name=name))

        return lc_messages


    def _create_model(self, llm_input: LLMInput) -> ChatAnthropic:
        """
        根据 LLMInput 配置创建 ExtendedChatOpenAI 实例。
        """
        # 提取基础参数
        model_kwargs = llm_input.parameters.copy()
        stream = model_kwargs.pop("stream", True) # 既然是 Worker，默认应该支持流式

        # 处理代理
        openai_proxy = llm_input.proxy_url if llm_input.proxy_url else None

        url = llm_input.api_host.rstrip("/").rstrip("/v1")
        return ChatAnthropic(
            model_name=llm_input.model_id,
            api_key=llm_input.api_key,
            base_url=url,
            model_kwargs=model_kwargs,
            anthropic_proxy=openai_proxy,
            timeout=llm_input.timeout,
            streaming=stream,
            stop=None
        )
