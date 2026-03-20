# backend/services/generation/worker/chat_worker.py

from abc import abstractmethod
from typing import AsyncGenerator, Any, List, Dict, Union, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
    AIMessageChunk
)
from langgraph.types import Command

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import BaseDecode, DefaultLangChainDecode
from backend.services.generation.graph_builders.factory import GraphBuilderFactory


class ChatWorker(AbstractGenerateWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，将底层模型的创建委托给子类，
    将 Agent 状态图的构建委托给 GraphBuilderFactory。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """

    def get_decode(self) -> BaseDecode:
        return DefaultLangChainDecode()

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        """
        将 LLMInput 中的字典格式消息转换为 LangChain 的 Message 对象。
        """
        lc_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "") or ''
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
        """
        根据 LLMInput 配置创建具体的底层大语言模型实例。
        由各提供商的 Worker 子类（如 OpenAiWorker, GoogleWorker 等）实现。
        """
        pass

    async def generate(
            self,
            llm_input: LLMInput
    ) -> AsyncGenerator[Tuple[str, Union[ToolMessage, AIMessageChunk, AIMessage, Dict[str, Any]]], None]:
        """
        启动 Agent 并流式返回执行过程中的事件。
        """

        # 1. 创建底层模型 (由子类实现)
        model = self._create_model(llm_input)

        # 2. 通过工厂获取 Agent 图 (彻底解耦图构建逻辑)
        graph_builder = GraphBuilderFactory.get_builder(llm_input.agent_config.agent_type)
        agent = graph_builder.build(model, llm_input.agent_config)

        # 3. 准备线程配置 (如果启用了 HITL 审核中断)
        thread_config = None
        if llm_input.agent_config.hitl_interrupt_on:
            thread_config = {"configurable": {"thread_id": llm_input.agent_config.thread_id}}

        # 4. 准备输入数据
        resume_payload = llm_input.agent_config.resume_payload
        if resume_payload:
            # 如果存在恢复载荷，说明是从 HITL 中断中恢复，使用 Command 恢复执行
            input_data = Command(resume=resume_payload)
        else:
            # 否则是全新的生成请求，传入历史消息
            messages = self._convert_messages(llm_input.context.messages)
            input_data = {"messages": messages}

        # 5. 执行流式输出
        async for stream1 in agent.astream(
                input=input_data,
                stream_mode=["messages", "updates"],
                config=thread_config,
                version="v2"
        ):
            mode = stream1["type"]
            event = stream1["data"]

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
                # mode == "messages"
                yield mode, event[0]

