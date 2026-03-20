from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from backend.services.generation.core.llm_io import AgentConfig

class BaseGraphBuilder(ABC):
    """
    Agent 状态图构建器抽象基类。
    负责将大语言模型与 Agent 配置组装成可执行的 LangGraph。
    """
    @abstractmethod
    def build(self, model: BaseChatModel, agent_config: AgentConfig) -> CompiledStateGraph:
        pass
