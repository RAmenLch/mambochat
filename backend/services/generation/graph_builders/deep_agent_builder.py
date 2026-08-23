# backend/services/generation/graph_builders/deep_agent_builder.py
#
# 【DEPRECATED - 已弃用，不再维护】
# 本文件为 DeepAgent（deepagents 库）专用图构建器。
# DeepAgent 已被淘汰，前端已无创建入口，本文件仅保留用于兼容存量数据。
# 新功能请基于 Mambo Agent（mambo_agents）实现。

from typing import List, Dict, Any
from langgraph.graph.state import CompiledStateGraph

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory
from backend.services.generation.agent.custom_middleware import ToolMessageOrderingMiddleware
from backend.services.generation.agent.api_backend import APIBackend
from backend.schemas.enums import BackendType

from backend.services.generation.agent.tree_extension import (
    TreeStateBackend,
    TreeCompositeBackend,
    TreeMiddleware,
    _NonExecutableBackendProxy,
)

def _create_backend_factory(
    mounted_backends: List[Dict[str, Any]],
    default_backend_id: str | None = None,
):
    def factory(runtime) -> TreeCompositeBackend:
        state_backend = TreeStateBackend(runtime)
        routes: Dict[str, Any] = {}

        if not mounted_backends:
            # No mounted backends — StateBackend is the sole default.
            return TreeCompositeBackend(default=state_backend, routes=routes)

        # Create all backend instances, keyed by their id.
        instances: Dict[str, Any] = {}
        for mb in mounted_backends:
            b_type = mb.get("backendType")
            b_name = mb.get("name")
            b_id = mb.get("id")
            config = mb.get("configData", {})
            tools_config = config.get("tools_config", {})
            execute_cfg = tools_config.get("execute", {})
            execute_enabled = execute_cfg.get("enabled", False)

            if b_type == BackendType.SSH.value:
                from backend.services.generation.agent.ssh_backend import PureSFTPBackend
                from backend.utils.ssh_utils import get_or_create_system_ssh_key
                priv_key_path = None
                if not config.get("password"):
                    priv_key_path, _ = get_or_create_system_ssh_key()

                backend = PureSFTPBackend(
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

            elif b_type == BackendType.API.value:
                backend = APIBackend(
                    backend_id=b_id,
                    backend_name=b_name,
                    edit_whitelist=config.get("edit_whitelist"),
                    edit_blacklist=config.get("edit_blacklist"),
                )
            else:
                continue

            # If execute is not enabled, wrap to hide SandboxBackendProtocol identity.
            if not execute_enabled:
                backend = _NonExecutableBackendProxy(backend)

            instances[b_id] = (backend, b_name)

        # Determine which backend becomes default.
        if default_backend_id and default_backend_id in instances:
            default_backend, _ = instances.pop(default_backend_id)
            # Mount remaining backends as routes.
            for b_id, (backend, b_name) in instances.items():
                routes[f"/{b_name}/"] = backend
            # Mount StateBackend at /this_chat_tmp/
            routes["/this_chat_tmp/"] = state_backend
        else:
            # No default selected — StateBackend remains default.
            default_backend = state_backend
            for b_id, (backend, b_name) in instances.items():
                routes[f"/{b_name}/"] = backend

        return TreeCompositeBackend(default=default_backend, routes=routes)

    return factory


class DeepAgentGraphBuilder(BaseGraphBuilder):
    """
    【DEPRECATED - 已弃用，不再维护】DeepAgent 架构的图构建器。
    请使用 MamboAgentGraphBuilder 替代。
    """

    def build(self, agent_config: AgentConfig, run_time_config: RunTimeConfig) -> CompiledStateGraph:
        from backend.services.generation.graph_builders.factory import GraphBuilderFactory
        from deepagents import create_deep_agent, CompiledSubAgent

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

        backend_factory = _create_backend_factory(
            mounted_backends=agent_config.mounted_backends or [],
            default_backend_id=agent_config.default_backend_id,
        )

        tools = [t for t in agent_config.tools] if agent_config.tools else []

        skill_paths: List[str] = []
        if agent_config.skills:
            for skill in agent_config.skills:
                skill_paths.append(f"/skills/{skill.name}")

        active_checkpointer = get_checkpointer()

        middlewares = [
            ToolMessageOrderingMiddleware(),
            TreeMiddleware(backend=backend_factory)
        ]

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
            interrupt_on=agent_config.hitl_interrupt_on,
        )
