# backend/services/generation/graph_builders/base_builder.py

from abc import ABC, abstractmethod
from langgraph.graph.state import CompiledStateGraph
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig

class BaseGraphBuilder(ABC):
    """
    Agent 状态图构建器抽象基类。
    负责将大语言模型与 Agent 配置组装成可执行的 LangGraph。
    """
    @abstractmethod
    def build(self, agent_config: AgentConfig, run_time_config: RunTimeConfig) -> CompiledStateGraph:
        pass
