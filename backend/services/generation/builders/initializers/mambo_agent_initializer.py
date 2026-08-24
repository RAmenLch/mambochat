# backend/services/generation/builders/initializers/mambo_agent_initializer.py

import asyncio
import json
import logging
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.schemas.enums import ToolReviewMode, AgentTypeEnum, ResourceType
from backend.models.agent_model import Agent
from backend.crud import mcp_crud, agent_crud, provider_crud, setting_crud, backend_crud, resource_crud

from backend.services.generation.core.llm_io import AgentConfig, ModelConfig, SecurityReviewAgentConfig
from backend.services.generation.builders.initializers.base_initializer import (
    AbstractAgentInitializer,
)
from backend.services.generation.builders.resource_dispatcher import ResourceDispatcher
from backend.services.generation.builders.param_utils import map_model_parameters

from mambo_agents.middleware.mcp import mcp_tool_name

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mambo_mcp_tool_provider import MamboMCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider
from backend.services.generation.tools.ask_user_tool_provider import AskUserToolProvider
from backend.services.generation.tools.kb_tool_provider import KBToolProvider
from backend.services.generation.tools.mambo_builtin_tool_provider import (
    MamboAgentBuiltinToolProvider,
)
from backend.services.generation.tools.web_search_tool_provider import WebSearchToolProvider
from backend.schemas.enums import WebSearchMode
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)


class MamboAgentInitializer(AbstractAgentInitializer):
    """Mambo Agent 初始化器。

    负责根据 Agent ORM 配置装配工具链、加载后端、初始化子代理，
    生成标准化的 AgentConfig。

    与 DeepAgentInitializer 的核心差异：
    - 使用 MamboAgentBuiltinToolProvider 拦截内置工具
    - 装配单个 Backend（通过 HybridWorkspaceBackend 支持 /.mambo/ 虚拟空间路由）
    """

    def __init__(
        self,
        db: AsyncSession,
        agent: Agent,
        resume_payload: Optional[Dict[str, Any]] = None,
        enable_tools: bool = False,
        enable_resource_merge: bool = False,
        external_tools: Optional[List[BaseTool]] = None,
        web_search_mode: Optional[WebSearchMode] = None,
        web_search_proxy_url: Optional[str] = None,
    ):
        self.db = db
        self.agent = agent
        self.resume_payload = resume_payload
        self.enable_tools = enable_tools
        self.enable_resource_merge = enable_resource_merge
        self.external_tools = external_tools or []
        self.web_search_mode = web_search_mode
        self.web_search_proxy_url = web_search_proxy_url

        self.providers: List[BaseToolProvider] = []
        self.hitl_interrupt_on: Dict[str, bool] = {}

    async def initialize(self) -> Tuple[AgentConfig, str]:
        extended_prompts: List[str] = []
        skills = []
        knowledge_bases = []

        file_service = FileService(self.db)
        dispatcher = ResourceDispatcher(self.db)

        if self.enable_resource_merge and self.agent.resourcePromptList:
            dispatch_result = await dispatcher.dispatch(self.agent.resourcePromptList)

            extended_prompts.extend(dispatch_result.get("system_prompts", []))
            extended_prompts.extend(dispatch_result.get("submessage_templates", []))
            knowledge_bases = dispatch_result.get("knowledge_bases", [])
            skills = dispatch_result.get("skills", [])

        if knowledge_bases:
            self.providers.append(KBToolProvider(self.db, knowledge_bases))

        # ---- 构建 skill_resource_roots（Mambo skills → /.mambo/skills/<name>/）----
        skill_resource_roots: Dict[str, str] = {}
        if skills and self.agent.resourcePromptList:
            from backend.services.generation.agent.backend_factory import build_skill_resource_roots
            skill_resource_roots = await build_skill_resource_roots(self.db, self.agent)

        # # DeepAgent 子代理仍然需要 skills 内容用于 VFS 注入
        # if skills:
        #     for skill in skills:
        #         for file_config in skill.files:
        #             try:
        #                 file_config.content = await file_service.get_text_content(
        #                     file_config.file_id
        #                 )
        #             except Exception:
        #                 file_config.content = ""

        mcp_server_configs = None
        mcp_exclude_tools = None

        if self.enable_tools:
            params = self.agent.parsed_model_parameters

            mcp_ids = self.agent.enabledMcpIds or []
            if mcp_ids:
                thin_provider = MamboMCPToolProvider(self.db, mcp_ids)
                loaded = await thin_provider.load_configs()

                if loaded:
                    self.providers.append(thin_provider)
                    mcp_server_configs = thin_provider.mcp_server_configs
                    mcp_exclude_tools = thin_provider.mcp_exclude_tools

                    # HITL：DB 审核配置 → mcp_tool_name 格式
                    mcp_tools_db = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                    for tool in mcp_tools_db:
                        if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                            sname = thin_provider.id_to_name.get(tool.server_id, tool.server_id)
                            effective_name = mcp_tool_name(sname, tool.name)
                            self.hitl_interrupt_on[effective_name] = True

            # WebSearch 内置搜索工具
            if self.web_search_mode is not None:
                self.providers.append(WebSearchToolProvider(self.web_search_mode, proxy_url=self.web_search_proxy_url))

            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

            enable_ask_user = params.get("enable_ask_user", False)
            if enable_ask_user:
                self.providers.append(AskUserToolProvider(enable_ask_user=True))

        # Mambo 内置工具拦截器
        builtin_provider = MamboAgentBuiltinToolProvider()
        self.providers.append(builtin_provider)

        all_tools: List[BaseTool] = list(self.external_tools)
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)

        # --- Backend 装配 ---
        from backend.services.generation.agent.backend_factory import build_mounted_backends
        mounted_backends = await build_mounted_backends(self.db, self.agent)

        # --- 子代理初始化 ---
        sub_configs: List[AgentConfig] = []

        # 从已加载的后端配置中自动注册后端级工具名称到 builtin_provider
        self._register_backend_tools(builtin_provider, mounted_backends)

        # 全局设置（子代理 & 安全审核共用）
        proxy_setting = await setting_crud.get_setting(self.db, "proxy_enabled")
        proxy_url_setting = await setting_crud.get_setting(self.db, "proxy_url")
        is_proxy_enabled = (
            proxy_setting.value == "True" if proxy_setting else False
        )
        global_proxy_url = proxy_url_setting.value if proxy_url_setting else None
        max_retries_setting = await setting_crud.get_setting(
            self.db, "default_max_retries"
        )
        global_max_retries = (
            int(max_retries_setting.value)
            if max_retries_setting and max_retries_setting.value
            else 3
        )
        timeout_setting = await setting_crud.get_setting(
            self.db, "default_timeout"
        )
        global_default_timeout = (
            int(timeout_setting.value)
            if timeout_setting and timeout_setting.value
            else 60
        )

        if self.agent.subAgents:
            sub_agents_db = await asyncio.gather(
                *[agent_crud.get_agent(self.db, sid) for sid in self.agent.subAgents]
            )

            for sub in sub_agents_db:
                if not sub:
                    continue

                atype = (
                    sub.AgentType.value
                    if hasattr(sub.AgentType, "value")
                    else sub.AgentType
                )
                if atype in (AgentTypeEnum.MAMBO.value, "Mambo"):
                    sub_init = MamboAgentInitializer(
                        db=self.db,
                        agent=sub,
                        resume_payload=self.resume_payload,
                        enable_tools=self.enable_tools,
                        enable_resource_merge=self.enable_resource_merge,
                        external_tools=self.external_tools,
                        web_search_mode=self.web_search_mode,
                        web_search_proxy_url=self.web_search_proxy_url,
                    )
                elif atype in (AgentTypeEnum.DEEP.value, "DeepAgent"):
                    from backend.services.generation.builders.initializers.deep_agent_initializer import (
                        DeepAgentInitializer,
                    )
                    sub_init = DeepAgentInitializer(
                        db=self.db,
                        agent=sub,
                        resume_payload=self.resume_payload,
                        enable_tools=self.enable_tools,
                        enable_resource_merge=self.enable_resource_merge,
                        external_tools=self.external_tools,
                        web_search_mode=self.web_search_mode,
                        web_search_proxy_url=self.web_search_proxy_url,
                    )
                else:
                    from backend.services.generation.builders.initializers.agent_react_initializer import (
                        AgentBasedReActInitializer,
                    )
                    sub_init = AgentBasedReActInitializer(
                        db=self.db,
                        agent=sub,
                        resume_payload=self.resume_payload,
                        enable_tools=self.enable_tools,
                        enable_resource_merge=self.enable_resource_merge,
                        external_tools=self.external_tools,
                        web_search_mode=self.web_search_mode,
                        web_search_proxy_url=self.web_search_proxy_url,
                    )

                sub_config, _ = await sub_init.initialize()

                if sub.aiModelId:
                    sub_model = await provider_crud.get_model(
                        self.db, sub.aiModelId
                    )
                    if sub_model and sub_model.provider:
                        proxy_url = None
                        if sub_model.provider.use_proxy and is_proxy_enabled:
                            proxy_url = global_proxy_url

                        api_params = map_model_parameters(sub.parsed_model_parameters)
                        api_params["_worker_type"] = sub_model.provider.worker_type

                        sub_model_max_retries = 0
                        sub_model_timeout = None
                        sub_model_stream_chunk_timeout = None
                        sub_model_context_length: Optional[int] = None
                        if sub_model.meta_config:
                            try:
                                meta = (
                                    json.loads(sub_model.meta_config)
                                    if isinstance(sub_model.meta_config, str)
                                    else sub_model.meta_config
                                )
                                sub_model_max_retries = int(
                                    meta.get("max_retries", 0)
                                )
                                raw_timeout = meta.get("timeout")
                                sub_model_timeout = (
                                    int(raw_timeout)
                                    if raw_timeout is not None
                                    else None
                                )
                                raw_stream_chunk_timeout = meta.get(
                                    "stream_chunk_timeout"
                                )
                                if raw_stream_chunk_timeout is not None:
                                    sub_model_stream_chunk_timeout = float(
                                        raw_stream_chunk_timeout
                                    )
                                raw_context_length = meta.get("context_length")
                                if raw_context_length is not None:
                                    sub_model_context_length = int(raw_context_length)
                            except (json.JSONDecodeError, ValueError, TypeError):
                                pass
                        sub_max_retries = (
                            sub_model_max_retries
                            if sub_model_max_retries > 0
                            else global_max_retries
                        )
                        sub_timeout = (
                            sub_model_timeout
                            if sub_model_timeout is not None
                            else global_default_timeout
                        )

                        sub_config.llm_config = ModelConfig(
                            model_id=sub_model.modelId,
                            api_host=sub_model.provider.apiHost,
                            api_key=sub_model.provider.apiKey,
                            proxy_url=proxy_url,
                            parameters=api_params,
                            max_retries=sub_max_retries,
                            timeout=sub_timeout,
                            stream_chunk_timeout=sub_model_stream_chunk_timeout,
                            context_length=sub_model_context_length,
                        )
                        sub_config.main_model_input_modalities = sorted(
                            self._parse_input_modalities(sub_model)
                        )

                sub_configs.append(sub_config)
                # 排除子代理的 MamboMCPToolProvider——子代理工具调用走
                # subagent_event 通道，由 SubAgentEventHandler 处理
                self.providers.extend([
                    p for p in sub_init.get_providers()
                    if not isinstance(p, MamboMCPToolProvider)
                ])

        base_prompt = self.agent.systemPrompt or ""
        additional_system_prompt = (
            "\n\n".join(extended_prompts) if extended_prompts else ""
        )
        final_system_prompt = (
            f"{base_prompt}\n\n{additional_system_prompt}".strip()
            if additional_system_prompt
            else base_prompt
        )

        # HITL: check if the effective default backend requires execute review.
        # When defaultBackendId is not explicitly set, the builder falls back to
        # the first backend in backendIds — so we must do the same here.
        if self.agent.backendIds:
            effective_default_id: str = self.agent.defaultBackendId or self.agent.backendIds[0]
            backends_db_for_hitl = await backend_crud.get_backends_by_ids(
                self.db, self.agent.backendIds
            )
            for b in backends_db_for_hitl:
                if b.id == effective_default_id and b.tools_config:
                    exec_cfg = b.tools_config.get("execute", {})
                    if exec_cfg.get("enabled") and exec_cfg.get("require_review"):
                        self.hitl_interrupt_on["execute"] = True
                    break

        # --- Mambo 专属参数：从 DB agentParameters 解析（结构化访问） ---
        from backend.schemas.agent import MamboAgentParametersSchema
        raw = self.agent.agentParameters or {}
        mambo_params: MamboAgentParametersSchema = (
            MamboAgentParametersSchema.model_validate(raw)
            if isinstance(raw, dict)
            else raw  # 已是结构化实例（一般不会发生，防御）
        )
        include_gp = mambo_params.include_general_purpose
        enable_sum = mambo_params.enable_summarization
        sum_config = mambo_params.summarization_config
        enable_planning = mambo_params.enable_planning
        enable_memory = mambo_params.enable_memory
        enable_show = mambo_params.enable_show
        memory_resource_ids = mambo_params.memory_resource_ids

        # 构建 memory_resource_roots（类似 skill_resource_roots）
        memory_roots: Dict[str, str] = {}
        if enable_memory and memory_resource_ids:
            memory_roots = await self._build_memory_roots(memory_resource_ids)

        # --- 版本控制配置解析 ---
        vc = mambo_params.version_control
        enable_vc = vc is not None and vc.enabled
        vc_config = None
        if enable_vc:
            vc_config = {
                "auto_snapshot": vc.auto_snapshot,
            }

        # --- 安全审核配置解析 ---
        security_review_config: Optional[SecurityReviewAgentConfig] = None
        security_review_llm_config: Optional[ModelConfig] = None
        sr = mambo_params.security_review
        if sr and sr.enabled:
            security_review_config = SecurityReviewAgentConfig(
                enabled=True,
                model_id=sr.model_id,
                system_prompt=sr.system_prompt,
                review_tools=sr.review_tools,
                agent_max_steps=sr.agent_max_steps,
            )
            if security_review_config.model_id:
                sr_model = await provider_crud.get_model(self.db, security_review_config.model_id)
                if sr_model and sr_model.provider:
                    proxy_url = None
                    if sr_model.provider.use_proxy and is_proxy_enabled:
                        proxy_url = global_proxy_url
                    api_params = map_model_parameters({})
                    api_params["_worker_type"] = sr_model.provider.worker_type

                    sr_max_retries = global_max_retries
                    sr_timeout = global_default_timeout
                    sr_stream_chunk_timeout = None
                    sr_context_length: Optional[int] = None
                    if sr_model.meta_config:
                        try:
                            meta = json.loads(sr_model.meta_config) if isinstance(sr_model.meta_config, str) else sr_model.meta_config
                            sr_max_retries = int(meta.get("max_retries", global_max_retries))
                            raw_t = meta.get("timeout")
                            sr_timeout = int(raw_t) if raw_t is not None else global_default_timeout
                            raw_sct = meta.get("stream_chunk_timeout")
                            sr_stream_chunk_timeout = float(raw_sct) if raw_sct is not None else None
                            raw_cl = meta.get("context_length")
                            sr_context_length = int(raw_cl) if raw_cl is not None else None
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass

                    security_review_llm_config = ModelConfig(
                        model_id=sr_model.modelId,
                        api_host=sr_model.provider.apiHost,
                        api_key=sr_model.provider.apiKey,
                        proxy_url=proxy_url,
                        parameters=api_params,
                        max_retries=sr_max_retries,
                        timeout=sr_timeout,
                        stream_chunk_timeout=sr_stream_chunk_timeout,
                        context_length=sr_context_length,
                    )

        # --- 多模态描述配置解析 ---
        # 每个模态槽位可独立绑定一个支持该模态的模型。能力未声明的模型视为
        # 纯文本模型，不参与描述；主模型原生支持的模态在 Builder 中透传。
        multimodal_describer_models: Dict[str, ModelConfig] = {}
        mm = mambo_params.multimodal_describer
        if mm and mm.enabled:
            mm_slots: Dict[str, Optional[str]] = {
                "image": mm.image_model_id,
                "audio": mm.audio_model_id,
                "video": mm.video_model_id,
                "file": mm.file_model_id,
            }
            for modality, model_id in mm_slots.items():
                if not model_id:
                    continue
                d_model = await provider_crud.get_model(self.db, model_id)
                if not d_model or not d_model.provider:
                    logger.warning(
                        "多模态描述：模态 %s 的模型 %s 不存在或无服务商，已跳过",
                        modality, model_id,
                    )
                    continue
                # 能力未声明 → 视为纯文本模型；声明中不含该模态 → 槽位无效
                if modality not in self._parse_input_modalities(d_model):
                    logger.warning(
                        "多模态描述：模型 %s(%s) 不支持模态 %s（能力未声明或声明不含该模态），已跳过",
                        d_model.modelId, d_model.name, modality,
                    )
                    continue
                proxy_url = None
                if d_model.provider.use_proxy and is_proxy_enabled:
                    proxy_url = global_proxy_url
                api_params = map_model_parameters({})
                api_params["_worker_type"] = d_model.provider.worker_type

                d_max_retries = global_max_retries
                d_timeout = global_default_timeout
                d_stream_chunk_timeout = None
                d_context_length: Optional[int] = None
                if d_model.meta_config:
                    try:
                        meta = (
                            json.loads(d_model.meta_config)
                            if isinstance(d_model.meta_config, str)
                            else d_model.meta_config
                        )
                        d_max_retries = int(meta.get("max_retries", global_max_retries))
                        raw_t = meta.get("timeout")
                        d_timeout = int(raw_t) if raw_t is not None else global_default_timeout
                        raw_sct = meta.get("stream_chunk_timeout")
                        d_stream_chunk_timeout = float(raw_sct) if raw_sct is not None else None
                        raw_cl = meta.get("context_length")
                        d_context_length = int(raw_cl) if raw_cl is not None else None
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass

                multimodal_describer_models[modality] = ModelConfig(
                    model_id=d_model.modelId,
                    api_host=d_model.provider.apiHost,
                    api_key=d_model.provider.apiKey,
                    proxy_url=proxy_url,
                    parameters=api_params,
                    max_retries=d_max_retries,
                    timeout=d_timeout,
                    stream_chunk_timeout=d_stream_chunk_timeout,
                    context_length=d_context_length,
                )

        # --- 任务循环配置解析 (GoalLoopMiddleware) ---
        goal_loop_config: Optional[Dict[str, Any]] = None
        gl = mambo_params.goal_loop
        if gl is not None:
            goal_loop_config = {
                "mode": gl.mode,
                "max_rounds": gl.max_rounds,
                "objective": gl.objective,
                "conditions": (
                    [c.model_dump() for c in gl.conditions]
                    if gl.conditions
                    else None
                ),
                "blocked_threshold": gl.blocked_threshold,
            }

        agent_config = AgentConfig(
            name=self.agent.name,
            description=self.agent.description or "",
            system_prompt=final_system_prompt,
            agent_type=AgentTypeEnum.MAMBO,
            tools=all_tools if all_tools else None,
            skills=skills if skills else None,
            sub_configs=sub_configs if sub_configs else None,
            hitl_interrupt_on=self.hitl_interrupt_on,
            resume_payload=self.resume_payload,
            mounted_backends=mounted_backends if mounted_backends else None,
            default_backend_id=self.agent.defaultBackendId,
            skill_resource_roots=skill_resource_roots if skill_resource_roots else None,
            include_general_purpose=include_gp,
            enable_summarization=enable_sum,
            summarization_config=sum_config.model_dump() if (enable_sum and sum_config) else None,
            enable_planning=enable_planning,
            enable_show=enable_show,
            memory_resource_roots=memory_roots if memory_roots else None,
            security_review_config=security_review_config,
            security_review_llm_config=security_review_llm_config,
            multimodal_describer_models=multimodal_describer_models or None,
            enable_version_control=enable_vc,
            version_control_config=vc_config,
            goal_loop_config=goal_loop_config,
            mcp_server_configs=mcp_server_configs,
            mcp_exclude_tools=mcp_exclude_tools,
            mcp_direct_tool_threshold=mambo_params.mcp_direct_tool_threshold,
        )

        return agent_config, additional_system_prompt

    async def _build_memory_roots(
        self, resource_ids: List[str]
    ) -> Dict[str, str]:
        """根据 memory_resource_ids 构建 {name: resource_id} 映射。

        注意：资源类型过滤和同名检测已在 Router 层
        (validate_memory_resources) 完成，此处仅做解析映射。

        Returns:
            {"resource_name": "res_xxx", ...}
        """
        roots: Dict[str, str] = {}
        for rid in resource_ids:
            res = await resource_crud.get_resource(self.db, rid)
            if res is None:
                continue
            roots[res.name] = res.id
        return roots

    @staticmethod
    def _parse_input_modalities(model: Any) -> set[str]:
        """解析模型声明的多模态输入能力。

        能力未声明（meta_config 缺失或无 input_modalities）→ 视为纯文本模型，
        返回空集。``document`` 归一化为 ``file``（与 mambo_agents 统一 block type 一致）。
        """
        meta = model.meta_config
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                return set()
        if not meta or not isinstance(meta, dict):
            return set()
        modalities = meta.get("input_modalities") or []
        normalized = set()
        for m in modalities:
            if m == "document":
                normalized.add("file")
            else:
                normalized.add(m)
        return normalized

    @staticmethod
    def _register_backend_tools(builtin_provider: "MamboAgentBuiltinToolProvider", mounted_backends: List[Dict[str, Any]]) -> None:
        """从已挂载的 backend 配置中收集其声明的工具名称，注册到 builtin_provider。

        通过读取后端类的 ``BACKEND_TOOL_NAMES`` 类属性实现自动发现，
        无需在 ``BUILTIN_TOOLS`` 中手动维护后端工具列表。
        """
        from backend.services.generation.agent.mambo_resource_backend import MamboResourceBackend

        for mb in mounted_backends:
            b_type = mb.get("backendType")
            if b_type != "resource":
                continue
            config = mb.get("configData", {})
            # 仅当 enable_version_editing 未显式关闭时才注册
            if config.get("enable_version_editing", True) is False:
                continue
            for name in MamboResourceBackend.BACKEND_TOOL_NAMES:
                builtin_provider.register_tool(name)

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers
