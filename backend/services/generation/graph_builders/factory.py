from backend.schemas.enums import AgentTypeEnum
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.react_builder import ReactGraphBuilder
from backend.services.generation.graph_builders.deep_agent_builder import DeepAgentGraphBuilder
from backend.services.generation.graph_builders.mambo_agent_builder import MamboAgentGraphBuilder

class GraphBuilderFactory:
    """
    Agent 构建器工厂。
    基于 AgentType 选择对应的图初始化策略 (符合开闭原则 OCP)。
    """
    _registry = {
        AgentTypeEnum.REACT: ReactGraphBuilder,
        AgentTypeEnum.DEEP: DeepAgentGraphBuilder,
        AgentTypeEnum.MAMBO: MamboAgentGraphBuilder,
    }

    @classmethod
    def get_builder(cls, agent_type: AgentTypeEnum) -> BaseGraphBuilder:
        builder_class = cls._registry.get(agent_type)
        if not builder_class:
            raise ValueError(f"Unsupported Agent Type: {agent_type}")
        return builder_class()
