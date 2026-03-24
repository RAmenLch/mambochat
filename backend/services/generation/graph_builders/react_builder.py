from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel

from backend.checkpointer import get_checkpointer
from backend.services.generation.agent.custom_middleware import ToolMessageOrderingMiddleware
from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from schemas.lc_agent import MamboContext


class ReactGraphBuilder(BaseGraphBuilder):
    """
    针对 ReAct 架构的图构建器。
    处理 HITL 中断、工具顺序中间件以及 Checkpointer 挂载。
    """
    def build(self, model: BaseChatModel, agent_config: AgentConfig) -> CompiledStateGraph:
        tools = [t for t in agent_config.tools] if agent_config.tools else []
        middlewares = []
        active_checkpointer = None

        # 挂载 HITL 与 顺序修复中间件
        if agent_config.hitl_interrupt_on:
            middlewares.append(HumanInTheLoopMiddleware(
                interrupt_on=agent_config.hitl_interrupt_on,
                description_prefix="需要审核的操作"
            ))
            middlewares.append(ToolMessageOrderingMiddleware())
            active_checkpointer = get_checkpointer()

        return create_agent(
            model,
            tools,
            middleware=middlewares,
            checkpointer=active_checkpointer,
            context_schema=MamboContext
        )
