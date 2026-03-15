# backend/services/generation/worker/chat_worker.py

from abc import abstractmethod
from typing import AsyncGenerator, Any, List, Dict, Union, Tuple, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
    AIMessageChunk
)
from langchain_core.tools import BaseTool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.types import Command
from backend.checkpointer import get_checkpointer
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.llm_io import LLMInput
from backend.services.generation.worker.decode import OpenAiDecode, BaseDecode
from schemas.agent import AgentState


class ChatWorker(AbstractGenerateWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ExtendedChatOpenAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """
    @staticmethod
    def get_decode() -> type[BaseDecode]:
        return BaseDecode

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

    @abstractmethod
    def _create_model(self, llm_input: LLMInput) -> BaseChatModel:
        pass

    async def generate(
        self,
        llm_input: LLMInput
    ) -> AsyncGenerator[Tuple[str, Union[ToolMessage, AIMessageChunk, AIMessage, Dict[str, Any]]], None]:

        model = self._create_model(llm_input)

        tools: List[BaseTool] = []
        if llm_input.tools:
            tools = [t for t in llm_input.tools if isinstance(t, BaseTool)]

        middlewares = []
        active_checkpointer = None
        thread_config = None  # 默认不传 config

        # 仅当明确需要审核时，才挂载中间件并启用 checkpointer
        if getattr(llm_input, 'hitl_interrupt_on', None):
            middleware = HumanInTheLoopMiddleware(
                interrupt_on=llm_input.hitl_interrupt_on,
                description_prefix="需要审核的操作"
            )
            middlewares.append(middleware)
            active_checkpointer = get_checkpointer()
            # 只有在使用 checkpointer 时，才需要配置 thread_id
            thread_config = {"configurable": {"thread_id": llm_input.thread_id}}

        agent = create_agent(
            model,
            tools,
            middleware=middlewares,  # 传递列表，即使为空也不会报 NoneType 错误
            checkpointer=active_checkpointer,
            state_schema=AgentState if middlewares else None
        )

        # 从 llm_input 中获取 resume_payload
        resume_payload = getattr(llm_input, 'resume_payload', None)
        if resume_payload:
            input_data = Command(resume=resume_payload)
        else:
            messages = self._convert_messages(llm_input.messages)
            input_data = {"messages": messages}

        async for mode, event in agent.astream(
                input=input_data,
                stream_mode=["messages", "updates"],
                config=thread_config,
                version="v2"
        ):
            if mode == "updates":
                if "model" in event:
                    for message in event["model"]['messages']:
                        yield mode, message
                if "tools" in event:
                    for message in event["tools"]['messages']:
                        yield mode, message
                if "__interrupt__" in event or "HumanInTheLoopMiddleware.after_model" in event:
                    yield mode, event
            else:
                yield mode, event[0]