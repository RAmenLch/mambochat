# backend/services/generation/graph_builders/mambo_agent_builder.py

from typing import List, Dict, Any, Sequence

from langgraph.graph.state import CompiledStateGraph

from mambo_agents import (
    create_mambo_agent,
    SubAgent,
    CompiledSubAgent,
    BackendProtocol,
    StateBackend,
    TempWorkspaceBackend,
)
from mambo_agents.backends.ssh import SshBackend

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory
from backend.services.generation.agent.mambo_api_backend import MamboAPIBackend
from backend.utils.ssh_utils import get_or_create_system_ssh_key
from backend.schemas.enums import BackendType


def _build_mambo_backend(
    mounted_backends: List[Dict[str, Any]],
    default_backend_id: str | None = None,
) -> BackendProtocol | None:
    """Build a single backend instance for mambo_agents.

    Mambo supports only one backend. Priority:
    1. default_backend_id (user-chosen default)
    2. First backend in mounted_backends list
    3. None (will use StateBackend by default in create_mambo_agent)

    The returned backend is wrapped in TempWorkspaceBackend so that
    middleware can write to /.mambo/ (StateBackend prefix).
    """
    if not mounted_backends:
        return None

    # Select the target backend
    target_mb: Dict[str, Any] | None = None

    if default_backend_id:
        for mb in mounted_backends:
            if mb.get("id") == default_backend_id:
                target_mb = mb
                break

    if target_mb is None:
        target_mb = mounted_backends[0]

    b_type = target_mb.get("backendType")
    b_id = target_mb.get("id")
    b_name = target_mb.get("name", "")
    config = target_mb.get("configData", {})

    if b_type == BackendType.SSH.value:
        priv_key_path = None
        if not config.get("password"):
            priv_key_path, _ = get_or_create_system_ssh_key()

        backend: BackendProtocol = SshBackend(
            host=config.get("hostname", ""),
            port=config.get("port", 22),
            username=config.get("username", ""),
            password=config.get("password"),
            key_filename=priv_key_path,
            remote_root=config.get("root_dir", "~"),
            edit_whitelist=_to_frozenset(config.get("edit_whitelist")),
            edit_blacklist=_to_frozenset(config.get("edit_blacklist")),
            ignore_dirs=_to_frozenset(config.get("ignore_dirs")),
        )

    elif b_type == BackendType.API.value:
        backend = MamboAPIBackend(
            backend_id=b_id,
            backend_name=b_name,
            edit_whitelist=config.get("edit_whitelist"),
            edit_blacklist=config.get("edit_blacklist"),
        )
    else:
        return None

    # Wrap with TempWorkspaceBackend so middleware can store under /.mambo/
    return TempWorkspaceBackend(backend)


def _to_frozenset(value: Any) -> frozenset[str] | None:
    """Convert a list/iterable to frozenset, or return None for empty."""
    if value is None:
        return None
    if isinstance(value, frozenset):
        return value if value else None
    s = frozenset(value)
    return s if s else None


class MamboAgentGraphBuilder(BaseGraphBuilder):
    """针对 Mambo Agent 架构的图构建器。

    使用 mambo_agents.create_mambo_agent() 代替 deepagents.create_deep_agent()。

    核心差异 vs DeepAgentGraphBuilder:
    - 单 Backend（无 CompositeBackend / 路由）
    - Tree 内置（无需 TreeMiddleware / TreeStateBackend）
    - Skills 格式不同（SkillSource tuples）
    - 支持 summarization / planning 等 mambo 内置能力
    """

    def build(
        self, agent_config: AgentConfig, run_time_config: RunTimeConfig
    ) -> CompiledStateGraph:
        from backend.services.generation.graph_builders.factory import (
            GraphBuilderFactory,
        )

        model = ModelFactory.create_model(agent_config.llm_config, run_time_config)

        # --- Build subagents ---
        compiled_subagents: List[SubAgent | CompiledSubAgent] = []

        if agent_config.sub_configs:
            for sub_config in agent_config.sub_configs:
                sub_builder = GraphBuilderFactory.get_builder(sub_config.agent_type)
                sub_graph = sub_builder.build(sub_config, run_time_config)

                compiled_subagents.append(
                    CompiledSubAgent(
                        name=sub_config.name,
                        description=sub_config.description
                        or f"Subagent for {sub_config.name}",
                        runnable=sub_graph,
                    )
                )

        # --- Build single backend ---
        backend = _build_mambo_backend(
            mounted_backends=agent_config.mounted_backends or [],
            default_backend_id=agent_config.default_backend_id,
        )

        # --- Tools ---
        tools = [t for t in agent_config.tools] if agent_config.tools else []

        # --- Skills (mambo format: Sequence[SkillSource]) ---
        skills: list[str | tuple[str, str]] = []
        if agent_config.skills:
            for skill in agent_config.skills:
                skills.append(f"/skills/{skill.name}")

        # --- Checkpointer ---
        checkpointer = get_checkpointer()

        # --- General Purpose (opt-in) ---
        include_general_purpose = getattr(agent_config, 'include_general_purpose', False)

        # --- Summarization (opt-in) ---
        summarization = None
        if getattr(agent_config, 'enable_summarization', False) and agent_config.summarization_config:
            cfg = agent_config.summarization_config
            summarization = {
                "trigger": (cfg["trigger_type"], cfg["trigger_value"]),
                "keep": (cfg["keep_type"], cfg["keep_value"]),
                "offload_to_backend": cfg.get("offload_to_backend", False),
            }

        return create_mambo_agent(
            name=agent_config.name,
            model=model,
            backend=backend,
            system_prompt=agent_config.system_prompt,
            subagents=compiled_subagents if compiled_subagents else None,
            include_general_purpose=include_general_purpose,
            summarization=summarization,
            tools=tools if tools else None,
            skills=skills if skills else None,
            checkpointer=checkpointer,
            interrupt_on=agent_config.hitl_interrupt_on if agent_config.hitl_interrupt_on else None,
        )
