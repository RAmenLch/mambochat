# backend/services/generation/graph_builders/deep_agent_builder.py

from typing import List
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent, CompiledSubAgent

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder


class DeepAgentGraphBuilder(BaseGraphBuilder):
    """
    针对 DeepAgent 架构的图构建器。
    基于 AgentConfig 树状结构，递归编译子代理图并将其封装挂载到父代理。
    """

    def build(self, model: BaseChatModel, agent_config: AgentConfig) -> CompiledStateGraph:
        # 局部导入以避免与 factory.py 产生循环引用
        from backend.services.generation.graph_builders.factory import GraphBuilderFactory

        compiled_subagents: List[CompiledSubAgent] = []

        if agent_config.sub_configs:
            for sub_config in agent_config.sub_configs:
                sub_builder = GraphBuilderFactory.get_builder(sub_config.agent_type)
                sub_graph = sub_builder.build(model, sub_config)

                compiled_subagents.append(
                    CompiledSubAgent(
                        name=sub_config.name,
                        description=sub_config.description or f"Subagent for {sub_config.name}",
                        runnable=sub_graph
                    )
                )

        tools = [t for t in agent_config.tools] if agent_config.tools else []

        skill_paths: List[str] = []
        if agent_config.skills:
            for skill in agent_config.skills:
                skill_paths.append(f"/skills/{skill.name}")

        active_checkpointer = get_checkpointer()

        return create_deep_agent(
            name=agent_config.name,
            model=model,
            system_prompt=agent_config.system_prompt,
            tools=tools,
            skills=skill_paths if skill_paths else None,
            subagents=compiled_subagents if compiled_subagents else None,
            checkpointer=active_checkpointer,
            interrupt_on=agent_config.hitl_interrupt_on
        )
