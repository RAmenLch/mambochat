# backend/services/generation/graph_builders/mambo_agent_builder.py
"""Mambo Agent 图构建器。

Backend 装配策略：
1. Resource Backend（mounted_backends 中的 RESOURCE 类型）→ MamboResourceBackend（优先）
2. SSH / API Backend → SshBackend / MamboAPIBackend（回退）
3. Skills（skill_resource_roots）→ shortcuts 方式挂载到 /.mambo/skills/<name>/

所有 Backend 统一通过 HybridWorkspaceBackend 路由：
  - /workspace/          → MamboResourceBackend 或 SSH/API Backend
  - /.mambo/             → 默认 StoreBackend
  - /.mambo/skills/      → MamboResourceBackend（shortcuts: {name: resource_id}）
"""

from typing import List, Dict, Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.graph.state import CompiledStateGraph

from mambo_agents import (
    create_mambo_agent,
    SubAgent,
    CompiledSubAgent,
    BackendProtocol,
    HybridWorkspaceBackend,
    StoreBackend,
)
from mambo_agents.backends.schemas import VirtualPath
from mambo_agents.backends.local import LocalBackend
from mambo_agents.middleware.security_review import SecurityReviewConfig

from backend.checkpointer import get_checkpointer
from backend.store import get_store
from backend.database import AsyncSessionLocal
from backend.services.generation.core.llm_io import AgentConfig, RunTimeConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder
from backend.services.generation.graph_builders.model_factory import ModelFactory
from backend.services.generation.agent.mambo_api_backend import MamboAPIBackend
from backend.services.generation.agent.mambo_resource_backend import MamboResourceBackend
from backend.schemas.enums import BackendType


# 缓存友好：限制单次 read / grep 的注入量，避免大工具结果拖垮缓存命中率
_READ_CHARS = 10_000
_GREP_MATCHES = 200

# 缓存友好：工具结果（execute/tree 等）估算 token 超过此值即落盘（eviction），
# 仅返回预览+文件路径给模型，避免大工具结果拖垮缓存命中率
_EVICT_TOKENS = 8_000


def _make_session_factory() -> Callable[[], AsyncSession]:
    """创建异步 session 工厂，用于 MamboResourceBackend 的数据库访问。"""
    return lambda: AsyncSessionLocal()


def _make_store_backend(
    store: "AsyncSqliteStore | None",
    thread_id: str | None,
) -> StoreBackend:
    """构造共享参数的 StoreBackend（real backend 与默认 /.mambo/ 空间共用）。

    thread_id 显式传入时（图外场景），写入会落到对应会话的 namespace；
    为 None 时（图内运行），运行时从 graph config 解析。
    """
    return StoreBackend(
        store=store,
        thread_id=thread_id,
        max_read_chars=_READ_CHARS,
        max_grep_matches=_GREP_MATCHES,
    )


def _build_mambo_backend(
    agent_config: AgentConfig,
    store: "AsyncSqliteStore | None" = None,
    thread_id: str | None = None,
) -> BackendProtocol | None:
    """构建 Mambo Agent 的完整 Backend 体系。

    装配逻辑（所有类型平等，不分优先级）：
    1. 按 default_backend_id 选一个作为 real_backend，否则取列表第一个
    2. 其余的（任意类型）→ virtual_workspaces[name]，AI 通过 /.mambo/{name}/ 访问
    3. Skills（skill_resource_roots）→ virtual_workspaces["skills"]

    Args:
        agent_config: Agent 配置。
        store: 共享的 LangGraph BaseStore 实例，传递给 StoreBackend 以保证持久化。
        thread_id: 可选，显式指定 StoreBackend 的会话隔离键（thread_id）。
            图构建路径不传（运行时从 graph config 解析）；独立场景
            （如消息创建时写入副本）必须传 chat_id，避免落到 __default__ namespace。

    Returns:
        HybridWorkspaceBackend 或 None（交给 create_mambo_agent 用默认 StoreBackend）
    """
    session_factory = _make_session_factory()
    virtual_workspaces: Dict[str, BackendProtocol] = {}

    mounted = agent_config.mounted_backends or []

    if not mounted:
        # 只有 skills / memory 则用 StoreBackend 兜底
        if agent_config.skill_resource_roots:
            virtual_workspaces["skills"] = MamboResourceBackend(
                resource_id=None,
                session_factory=session_factory,
                shortcuts=agent_config.skill_resource_roots,
                workspace_root=VirtualPath("/workspace"),
                max_read_chars=_READ_CHARS,
                max_grep_matches=_GREP_MATCHES,
            )
        if agent_config.memory_resource_roots:
            virtual_workspaces["memory"] = MamboResourceBackend(
                resource_id=None,
                session_factory=session_factory,
                shortcuts=agent_config.memory_resource_roots,
                workspace_root=VirtualPath("/workspace"),
                enable_version_editing=False,
                max_read_chars=_READ_CHARS,
                max_grep_matches=_GREP_MATCHES,
            )
        # 始终使用 persisted StoreBackend，避免 create_mambo_agent 内部
        # 用 store=None 创建无持久化的 StoreBackend 兜底
        if thread_id is not None:
            # 图外场景（如消息创建时写入副本）：覆盖默认 /.mambo/ StoreBackend，
            # 使其写入目标会话的 namespace
            virtual_workspaces["."] = _make_store_backend(store, thread_id)
        return HybridWorkspaceBackend(
            real_backend=_make_store_backend(store, thread_id),
            virtual_workspaces=virtual_workspaces if virtual_workspaces else None,
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    # ---- 1. 确定 real_backend：default_backend_id > 列表第一位 ----
    real_be: BackendProtocol | None = None
    target_mb = _pick_default(mounted, agent_config.default_backend_id)
    if target_mb:
        real_be = _build_any_backend(target_mb, session_factory)

    # ---- 2. 其余所有后端 → virtual_workspaces[name] ----
    real_id = _resolve_real_backend_id(mounted, agent_config.default_backend_id)
    for mb in mounted:
        if mb.get("id") == real_id:
            continue
        name = mb.get("name", "")
        if not name:
            continue
        be = _build_any_backend(mb, session_factory)
        if be:
            virtual_workspaces[name] = be

    # ---- 3. Skills ----
    # Skills are shortcut-only backends (no workspace root).  They always
    # use legacy flat-file mode — individual skill files are NOT versioned.
    if agent_config.skill_resource_roots:
        virtual_workspaces["skills"] = MamboResourceBackend(
            resource_id=None,
            session_factory=session_factory,
            shortcuts=agent_config.skill_resource_roots,
            workspace_root=VirtualPath("/workspace"),
            enable_version_editing=False,
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    # ---- 4. Memory（长期记忆） ----
    # Memory is shortcut-only too.  Memory files like Agent.md are loaded
    # from resource folders but should appear as flat files.
    if agent_config.memory_resource_roots:
        virtual_workspaces["memory"] = MamboResourceBackend(
            resource_id=None,
            session_factory=session_factory,
            shortcuts=agent_config.memory_resource_roots,
            workspace_root=VirtualPath("/workspace"),
            enable_version_editing=False,
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    # ---- 5. 组装 ----
    if real_be is None:
        real_be = _make_store_backend(store, thread_id)

    if thread_id is not None:
        # 图外场景：覆盖默认 /.mambo/ StoreBackend，写入目标会话的 namespace
        virtual_workspaces["."] = _make_store_backend(store, thread_id)

    return HybridWorkspaceBackend(
        real_backend=real_be,
        virtual_workspaces=virtual_workspaces if virtual_workspaces else None,
        max_read_chars=_READ_CHARS,
        max_grep_matches=_GREP_MATCHES,
    )


def _build_any_backend(
    mb: Dict[str, Any],
    session_factory: Callable[[], AsyncSession],
) -> BackendProtocol | None:
    """构建任意类型的 Backend 实例（SSH / API / RESOURCE）。"""
    b_type = mb.get("backendType")
    b_id = mb.get("id")
    b_name = mb.get("name", "")
    config = mb.get("configData", {})

    if b_type == BackendType.SSH.value:
        from mambo_agents.backends.ssh import SshBackend
        from backend.utils.ssh_utils import get_or_create_system_ssh_key
        priv_key_path = None
        if not config.get("password"):
            priv_key_path, _ = get_or_create_system_ssh_key()
        # Extract execute enable flag from tools_config
        tools_config = config.get("tools_config", {})
        execute_cfg = tools_config.get("execute", {})
        execute_enabled = execute_cfg.get("enabled", False)
        return SshBackend(
            host=config.get("hostname", ""),
            port=config.get("port", 22),
            username=config.get("username", ""),
            password=config.get("password"),
            key_filename=priv_key_path,
            remote_root=config.get("root_dir", "~"),
            enable_execute=execute_enabled,
            edit_whitelist=_to_virtual_path_frozenset(config.get("edit_whitelist")),
            edit_blacklist=_to_virtual_path_frozenset(config.get("edit_blacklist")),
            ignore_dirs=_to_frozenset(config.get("ignore_dirs")),
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    elif b_type == BackendType.API.value:
        tools_config = config.get("tools_config", {})
        execute_cfg = tools_config.get("execute", {})
        execute_enabled = execute_cfg.get("enabled", False)
        return MamboAPIBackend(
            backend_id=b_id,
            backend_name=b_name,
            edit_whitelist=config.get("edit_whitelist"),
            edit_blacklist=config.get("edit_blacklist"),
            ignore_dirs=config.get("ignore_dirs"),
            enable_execute=execute_enabled,
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    elif b_type == BackendType.RESOURCE.value:
        return MamboResourceBackend(
            resource_id=config.get("resource_id", ""),
            session_factory=session_factory,
            edit_whitelist=_to_frozenset(config.get("edit_whitelist")),
            edit_blacklist=_to_frozenset(config.get("edit_blacklist")),
            enable_version_editing=config.get("enable_version_editing", True),
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    elif b_type == BackendType.LOCAL.value:
        from pathlib import Path
        tools_config = config.get("tools_config", {})
        execute_cfg = tools_config.get("execute", {})
        execute_enabled = execute_cfg.get("enabled", False)
        root_dir = config.get("root_dir") or str(Path.home())
        if root_dir == "~":
            root_dir = str(Path.home())
        return LocalBackend(
            root_dir=root_dir,
            enable_execute=execute_enabled,
            edit_whitelist=_to_virtual_path_frozenset(config.get("edit_whitelist")),
            edit_blacklist=_to_virtual_path_frozenset(config.get("edit_blacklist")),
            ignore_dirs=_to_frozenset(config.get("ignore_dirs")),
            max_read_chars=_READ_CHARS,
            max_grep_matches=_GREP_MATCHES,
        )

    return None


def _resolve_real_backend_id(
    backends: List[Dict[str, Any]],
    default_backend_id: str | None = None,
) -> str | None:
    """解析哪个 Backend ID 会被选作 real_backend。"""
    if not backends:
        return None
    if default_backend_id:
        for mb in backends:
            if mb.get("id") == default_backend_id:
                return default_backend_id
    return backends[0].get("id")


def _pick_default(
    backends: List[Dict[str, Any]],
    default_backend_id: str | None = None,
) -> Dict[str, Any]:
    """按 default_backend_id 优先，否则取第一个。"""
    if default_backend_id:
        for mb in backends:
            if mb.get("id") == default_backend_id:
                return mb
    return backends[0]


def _to_frozenset(value: Any) -> frozenset[str] | None:
    """Convert a list/iterable to frozenset, or return None for empty."""
    if value is None:
        return None
    if isinstance(value, frozenset):
        return value if value else None
    s = frozenset(value)
    return s if s else None


def _to_virtual_path_frozenset(value: Any) -> frozenset[VirtualPath] | None:
    """Convert a list/iterable of path strings to frozenset[VirtualPath], or return None for empty."""
    if value is None:
        return None
    if isinstance(value, frozenset):
        if not value:
            return None
        # Already VirtualPath instances or strings → wrap in VirtualPath
        return frozenset(
            p if isinstance(p, VirtualPath) else VirtualPath(p) for p in value
        )
    if not value:
        return None
    return frozenset(VirtualPath(p) for p in value)


class MamboAgentGraphBuilder(BaseGraphBuilder):
    """针对 Mambo Agent 架构的图构建器。

    核心差异 vs DeepAgentGraphBuilder:
    - Backend 通过 HybridWorkspaceBackend 路由 /.mambo/ 虚拟空间
    - 支持资源文件夹挂载（MamboResourceBackend）
    - Skills 通过 shortcuts 挂载到 /.mambo/skills/
    - Tree 内置（无需 TreeMiddleware / TreeStateBackend）
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

        # --- MCP middleware（从 AgentConfig 中的 server configs 构建）---
        mcp_middleware = None
        if agent_config.mcp_server_configs:
            from mambo_agents.middleware.mcp import MCPMiddleware
            mcp_middleware = MCPMiddleware(
                servers=agent_config.mcp_server_configs,
                exclude_tools=agent_config.mcp_exclude_tools,
                direct_tool_threshold=agent_config.mcp_direct_tool_threshold,
            )

        # --- Build backend（统一入口：资源挂载 + SSH/API + Skills shortcuts）---
        store = get_store()
        backend = _build_mambo_backend(agent_config, store=store)

        # --- Tools ---
        tools = [t for t in agent_config.tools] if agent_config.tools else []

        # --- Skills → SkillsMiddleware 通过 backend 扫描 /.mambo/skills/ 路径下的 SKILL.md ---
        # shortcuts {name: resource_id} → 每个 skill 文件夹直接展开在 /.mambo/skills/<name>/
        # SkillsMiddleware: ls → 发现子目录 → download_files → 解析 frontmatter → 注入系统提示词
        skills_sources: list[str] | None = None
        if agent_config.skill_resource_roots:
            skills_sources = ["/.mambo/skills/"]

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

        # --- Planning (opt-in, default on) ---
        _plan_middleware = None
        if getattr(agent_config, 'enable_planning', True):
            from mambo_agents.middleware.planning import MamboPlanMiddleware
            _plan_middleware = [MamboPlanMiddleware()]

        # --- Security Review (opt-in) ---
        security_review = None
        sr_config = getattr(agent_config, 'security_review_config', None)
        if sr_config and sr_config.enabled:
            if agent_config.security_review_llm_config:
                review_model = ModelFactory.create_model(
                    agent_config.security_review_llm_config, run_time_config
                )
            else:
                review_model = model
            review_tools = sr_config.review_tools
            if review_tools and len(review_tools) > 0:
                review_tools = frozenset(review_tools)
            else:
                review_tools = "all"
            tool_unpackers = None
            if mcp_middleware is not None:
                tool_unpackers = [mcp_middleware.tool_unpacker]

            security_review = SecurityReviewConfig(
                model=review_model,
                system_prompt=sr_config.system_prompt,
                review_tools=review_tools,
                review_mode="agent",
                agent_max_steps=sr_config.agent_max_steps or 10,
                tool_unpackers=tool_unpackers,
            )

        # --- Memory sources（长期记忆） ---
        memory_sources: list[VirtualPath] | None = None
        if agent_config.memory_resource_roots:
            memory_sources = [
                VirtualPath(f"/.mambo/memory/{name}")
                for name in agent_config.memory_resource_roots
            ]

        # --- Version Control middleware (opt-in) ---
        _version_control_middleware = None
        if getattr(agent_config, 'enable_version_control', False):
            from mambo_agents.middleware.version_control import (
                VersionStore,
                VersionControlMiddleware,
            )
            vc_cfg = agent_config.version_control_config or {}
            vc_store = VersionStore(store=store)
            # Monitor /workspace — all backends (SSH/Resource/API) present files under this path
            _version_control_middleware = VersionControlMiddleware(
                store=vc_store,
                backend=backend,
                whitelist_folders=[VirtualPath("/workspace")],
            )

        # --- Show tool middleware (opt-in, default on) ---
        _show_middleware = None
        if getattr(agent_config, 'enable_show', True):
            from backend.services.generation.agent.show_middleware import ShowMiddleware
            _show_middleware = ShowMiddleware(
                backend=backend,
                session_factory=_make_session_factory(),
            )

        # --- Merge middlewares ---
        _middlewares: list = []
        if _plan_middleware:
            _middlewares.extend(_plan_middleware)
        if _version_control_middleware:
            _middlewares.append(_version_control_middleware)
        if _show_middleware:
            _middlewares.append(_show_middleware)

        # --- MCP middleware（插到最前面，让 system prompt 尽早注入）---
        if mcp_middleware is not None:
            _middlewares.insert(0, mcp_middleware)

        return create_mambo_agent(
            name=agent_config.name,
            model=model,
            backend=backend,
            store=store,
            system_prompt=(
                "Follow the system instructions below and use the available tools as needed."
                if agent_config.system_prompt
                else None
            ),
            subagents=compiled_subagents if compiled_subagents else None,
            include_general_purpose=include_general_purpose,
            summarization=summarization,
            tools=tools if tools else None,
            skills=skills_sources,
            memory_sources=memory_sources,
            middleware=_middlewares if _middlewares else None,
            checkpointer=checkpointer,
            interrupt_on=agent_config.hitl_interrupt_on if agent_config.hitl_interrupt_on else None,
            security_review=security_review,
            tool_token_limit_before_evict=_EVICT_TOKENS,
        )
