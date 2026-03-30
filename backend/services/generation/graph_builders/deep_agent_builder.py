# backend/services/generation/graph_builders/deep_agent_builder.py

from typing import List, Dict, Any
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent, CompiledSubAgent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.state import StateBackend

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory
from backend.services.generation.agent.custom_middleware import ToolMessageOrderingMiddleware
from backend.services.generation.agent.ssh_backend import PureSFTPBackend
from backend.utils.ssh_utils import get_or_create_system_ssh_key
from backend.schemas.enums import BackendType


def _create_backend_factory(mounted_backends: List[Dict[str, Any]]):
    """
    创建 Backend Factory，供 deepagents 内部调用。
    使用 CompositeBackend 将不同的远程存储路由到指定的虚拟目录，
    保留 StateBackend 作为默认的临时状态存储。
    """
    def factory(runtime) -> CompositeBackend:
        default_backend = StateBackend(runtime)
        routes = {}

        for mb in mounted_backends:
            b_type = mb.get("backendType")
            b_name = mb.get("name")
            config = mb.get("configData", {})

            if b_type == BackendType.SSH.value:
                priv_key_path = None
                if not config.get("password"):
                    priv_key_path, _ = get_or_create_system_ssh_key()

                ssh_backend = PureSFTPBackend(
                    hostname=config.get("hostname"),
                    port=config.get("port", 22),
                    username=config.get("username"),
                    password=config.get("password"),
                    key_filename=priv_key_path,
                    root_dir=config.get("root_dir", "/"),
                    edit_whitelist=config.get("edit_whitelist"),
                    edit_blacklist=config.get("edit_blacklist"),
                    ignore_dirs=config.get("ignore_dirs")
                )

                route_prefix = f"/{b_name}/"
                routes[route_prefix] = ssh_backend

        return CompositeBackend(default=default_backend, routes=routes)

    return factory


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

        backend_factory = _create_backend_factory(agent_config.mounted_backends or [])

        return create_deep_agent(
            name=agent_config.name,
            model=model,
            system_prompt=agent_config.system_prompt,
            middleware=middlewares,
            tools=tools,
            skills=skill_paths if skill_paths else None,
            subagents=compiled_subagents if compiled_subagents else None,
            checkpointer=active_checkpointer,
            backend=backend_factory,
            interrupt_on=agent_config.hitl_interrupt_on
        )

