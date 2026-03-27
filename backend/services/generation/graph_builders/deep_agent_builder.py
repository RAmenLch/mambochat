# backend/services/generation/graph_builders/deep_agent_builder.py

from typing import List
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent, CompiledSubAgent

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory
from backend.services.generation.agent.custom_middleware import ToolMessageOrderingMiddleware


class DeepAgentGraphBuilder(BaseGraphBuilder):
    """
    针对 DeepAgent 架构的图构建器。
    基于 AgentConfig 树状结构，递归编译子代理图并将其封装挂载到父代理。
    """

    def build(self, agent_config: AgentConfig, run_time_config: RunTimeConfig) -> CompiledStateGraph:
        from backend.services.generation.graph_builders.factory import GraphBuilderFactory

        model = ModelFactory.create_model(agent_config.llm_config, run_time_config)

        compiled_subagents: List[CompiledSubAgent] = []

        if agent_config.sub_configs:
            for sub_config in agent_config.sub_configs:
                sub_builder = GraphBuilderFactory.get_builder(sub_config.agent_type)
                sub_graph = sub_builder.build(sub_config, run_time_config)

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

        middlewares = [ToolMessageOrderingMiddleware()]

        return create_deep_agent(
            name=agent_config.name,
            model=model,
            system_prompt=agent_config.system_prompt,
            middleware=middlewares,
            tools=tools,
            skills=skill_paths if skill_paths else None,
            subagents=compiled_subagents if compiled_subagents else None,
            checkpointer=active_checkpointer,
            interrupt_on=agent_config.hitl_interrupt_on
        )
