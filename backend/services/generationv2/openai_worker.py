import json
from typing import AsyncGenerator, Any, List, Dict, Union, Optional, Tuple

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
    BaseMessageChunk, AIMessageChunk
)
from langchain_core.tools import BaseTool
from langchain.agents import create_agent
from backend.services.generationv2.extended_chat_openai_model import  ExtendedChatOpenAI
from backend.services.generationv2.base import AbstractGenerateWorker
from backend.services.generationv2.llm_io import LLMInput


class OpenAiWorker(AbstractGenerateWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ExtendedChatOpenAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
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
                lc_messages.append(AIMessage(content=content, name=name))
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
                lc_messages.append(HumanMessage(content=content, name=name))

        return lc_messages

    def _create_model(self, llm_input: LLMInput) -> ExtendedChatOpenAI:
        """
        根据 LLMInput 配置创建 ExtendedChatOpenAI 实例。
        """
        # 提取基础参数
        model_kwargs = llm_input.parameters.copy()
        stream = model_kwargs.pop("stream", True) # 既然是 Worker，默认应该支持流式

        # 处理代理
        openai_proxy = llm_input.proxy_url if llm_input.proxy_url else None

        return ExtendedChatOpenAI(
            model=llm_input.model_id,
            api_key=llm_input.api_key,
            base_url=llm_input.api_host.rstrip("/"),
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.timeout,
            streaming=stream
        )

    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[Tuple[str, Union[ToolMessage,AIMessageChunk, AIMessage, Dict[str, Any]]], None]:

        model = self._create_model(llm_input)

        tools: List[BaseTool] = []
        if llm_input.tools:

            tools = [t for t in llm_input.tools if isinstance(t, BaseTool)]

        messages = self._convert_messages(llm_input.messages)
        agent = create_agent(model,tools)

        async for mode,event in agent.astream(
                input={"messages": messages},
                stream_mode=["messages","updates"]
        ):
            if mode == "updates":
                if "model" in event:
                    for message in event["model"]['messages']:
                        yield mode,message
                if "tools" in event:
                    for message in event["tools"]['messages']:
                        yield mode,message
            else:
                yield mode,event[0]

