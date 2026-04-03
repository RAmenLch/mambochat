# backend/services/generation/graph_builders/react_builder.py

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.graph.state import CompiledStateGraph

from backend.checkpointer import get_checkpointer
from backend.services.generation.agent.custom_middleware import ToolMessageOrderingMiddleware
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory


class ReactGraphBuilder(BaseGraphBuilder):
    """
    针对 ReAct 架构的图构建器。
    处理 HITL 中断、工具顺序中间件以及 Checkpointer 挂载。
    """
    def build(self, agent_config: AgentConfig, run_time_config: RunTimeConfig) -> CompiledStateGraph:
        model = ModelFactory.create_model(agent_config.llm_config, run_time_config)

        tools = [t for t in agent_config.tools] if agent_config.tools else []
        middlewares = []
        active_checkpointer = get_checkpointer()

        if agent_config.hitl_interrupt_on:
            middlewares.append(HumanInTheLoopMiddleware(
                interrupt_on=agent_config.hitl_interrupt_on,
                description_prefix="需要审核的操作"
            ))
            middlewares.append(ToolMessageOrderingMiddleware())

        return create_agent(
            name =agent_config.name,
            model=model,
            tools=tools,
            middleware=middlewares,
            checkpointer=active_checkpointer
        )
