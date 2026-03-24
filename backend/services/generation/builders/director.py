# backend/services/generation/builders/director.py

import json
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.crud import provider_crud
from backend.schemas import enums as schemas_enums
from backend.schemas.enums import ChatMode, AgentTypeEnum
from backend.schemas.message import ReviewToolContent, McpToolContent
from backend.schemas.provider import AIModel
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS

from backend.services.generation.core.llm_io import LLMInput, ModelConfig
from backend.services.generation.builders.material_loader import GenerationMaterialLoader, GenerationMaterials
from backend.services.generation.builders.context_builder import MessageContextBuilder
from backend.services.generation.builders.initializers.chat_react_initializer import ChatBasedReActInitializer
from backend.services.generation.builders.initializers.agent_react_initializer import AgentBasedReActInitializer
from backend.services.generation.builders.initializers.deep_agent_initializer import DeepAgentInitializer
from backend.services.generation.tools.base_tool_provider import BaseToolProvider


class LLMInputDirector:
    """
    LLM 输入装配指挥官。
    对外暴露 Fluent API，对内统筹物料加载、模型配置、Agent 初始化与消息上下文装配。
    """

    def __init__(self, db: AsyncSession, chat_id: str):
        if not chat_id:
            raise ValueError("LLMInputDirector requires a chat_id")

        self.db = db
        self.chat_id = chat_id

        # --- 配置状态 ---
        self._cutoff_message_id: Optional[str] = None
        self._cutoff_include: bool = False
        self._slice_range: Optional[slice] = None
        self._head_tail: Optional[Tuple[int, int]] = None
        self._type_filter: Optional[Set[str]] = None
        self._enable_cpl_filter: bool = False
        self._enable_image_with_model: bool = False
        self._enable_zip_history: bool = True
        self._global_model_keys: List[str] = []
        self._system_prompt_override: Optional[str] = None
        self._history_override: Optional[List[Any]] = None
        self._enable_resource_merge: bool = False
        self._content_limit: Optional[int] = None
        self._flatten_history: bool = False
        self._append_prompt: Optional[str] = None
        self._tools: Optional[List[BaseTool]] = None
        self._enable_max_context_messages: bool = False
        self._enable_tools: bool = False

        self._force_normal_mode: bool = False

        # --- 运行时缓存 ---
        self._providers: List[BaseToolProvider] = []

    # ==================== Fluent API ====================

    def slice_until_message(self, message_id: str, include_target: bool = False) -> "LLMInputDirector":
        self._cutoff_message_id = message_id
        self._cutoff_include = include_target
        return self

    def slice(self, start: int, end: Optional[int] = None) -> "LLMInputDirector":
        self._slice_range = slice(start, end)
        return self

    def slice_head_tail(self, head: int, tail: int) -> "LLMInputDirector":
        self._head_tail = (head, tail)
        return self

    def filter_sub_message_types(self, *types: str) -> "LLMInputDirector":
        self._type_filter = set(types)
        return self

    def enable_cpl_filter(self) -> "LLMInputDirector":
        self._enable_cpl_filter = True
        return self

    def enable_image_with_model(self) -> "LLMInputDirector":
        self._enable_image_with_model = True
        return self

    def disable_zip_history(self) -> "LLMInputDirector":
        self._enable_zip_history = False
        return self

    def use_global_model(self, setting_keys: List[str]) -> "LLMInputDirector":
        self._global_model_keys = setting_keys
        return self

    def set_system_prompt(self, prompt: str) -> "LLMInputDirector":
        self._system_prompt_override = prompt
        return self

    def set_history_override(self, history: List[Any]) -> "LLMInputDirector":
        self._history_override = history
        return self

    def enable_resource_prompt_merge(self) -> "LLMInputDirector":
        self._enable_resource_merge = True
        return self

    def limit_sub_message_content(self, max_length: int) -> "LLMInputDirector":
        self._content_limit = max_length
        return self

    def flatten_history_to_single_user_message(self) -> "LLMInputDirector":
        self._flatten_history = True
        return self

    def append_user_message(self, content: str) -> "LLMInputDirector":
        self._append_prompt = content
        return self

    def set_tools(self, tools: List[BaseTool]) -> "LLMInputDirector":
        self._tools = tools
        return self

    def enable_max_context_messages(self) -> "LLMInputDirector":
        self._enable_max_context_messages = True
        return self

    def enable_tools(self) -> "LLMInputDirector":
        self._enable_tools = True
        return self

    def force_normal_mode(self) -> "LLMInputDirector":
        """
        强制使用普通聊天模式。
        忽略会话绑定的 Agent 配置，统一使用 ChatBasedReActInitializer (ReActAgent)。
        适用于标题生成、历史压缩等内部简单任务。
        """
        self._force_normal_mode = True
        return self

    # ==================== 核心构建逻辑 ====================

    async def build(self) -> LLMInput:
        """统筹装配流程，生成最终的 LLMInput 对象。"""

        # 1. 委托 Loader 获取基础物料 (解耦 DB 查询)
        materials = await GenerationMaterialLoader.load(
            db=self.db,
            chat_id=self.chat_id,
            cutoff_message_id=self._cutoff_message_id,
            cutoff_include=self._cutoff_include,
            history_override=self._history_override
        )

        # 2. 解析模型与 Provider
        model = await self._resolve_model(materials)
        provider = model.provider

        # 3. 判断模式并提取活动配置
        is_agent_mode = not self._force_normal_mode and \
                        (materials.chat.chatMode == ChatMode.AGENT.value and materials.agent is not None)

        active_params = materials.agent.modelParameters if is_agent_mode else materials.chat.modelParameters

        # 4. 构建 LLMConfig
        api_params = {}
        if not self._global_model_keys:
            api_params = self._map_parameters(active_params)

        proxy_url = None
        if provider.use_proxy and materials.settings.get("proxy_enabled") == "True":
            proxy_url = materials.settings.get("proxy_url")

        llm_config = ModelConfig(
            model_id=model.modelId,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            parameters=api_params
        )

        # 5. 解析 HITL 恢复载荷
        resume_payload = self._extract_resume_payload(materials.target_msg)
        thread_id = self.chat_id

        # 6. 智能路由 Initializer 进行 Agent 初始化
        if is_agent_mode:
            if materials.agent.AgentType == AgentTypeEnum.DEEP.value or materials.agent.AgentType == AgentTypeEnum.DEEP:
                initializer = DeepAgentInitializer(
                    db=self.db,
                    agent=materials.agent,
                    thread_id=thread_id,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools
                )
            else:
                initializer = AgentBasedReActInitializer(
                    db=self.db,
                    agent=materials.agent,
                    thread_id=thread_id,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools
                )
            base_system_prompt = materials.agent.systemPrompt or ""
        else:
            initializer = ChatBasedReActInitializer(
                db=self.db,
                chat=materials.chat,
                thread_id=thread_id,
                resume_payload=resume_payload,
                enable_tools=self._enable_tools,
                enable_resource_merge=self._enable_resource_merge,
                external_tools=self._tools
            )
            base_system_prompt = materials.chat.systemPrompt or ""

        agent_config, extended_prompt = await initializer.initialize()
        self._providers = initializer.get_providers()

        # 7. 恢复 Provider 的执行状态，处理跨 HTTP 请求（如 HITL 中断恢复）导致的内存状态丢失
        if self._cutoff_message_id and materials.target_msg:
            for sub in materials.target_msg.sub_messages:
                if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                    if sub.status in [schemas_enums.MessageStatus.GENERATING.value, schemas_enums.MessageStatus.PENDING_REVIEW.value]:
                        try:
                            content_obj = McpToolContent.from_json_string(sub.content)
                            if content_obj and content_obj.tool_call_id:
                                for tp in self._providers:
                                    if tp.matches_tool_name(content_obj.name):
                                        tp.restore_state(content_obj.tool_call_id, sub.id, content_obj)
                                        break
                        except (ValueError, TypeError, ImportError):
                            pass

        # 校验 HITL 冲突
        if not self._cutoff_message_id and agent_config.hitl_interrupt_on:
            raise ValueError("Build failed: assistant_message_id is required when HITL is enabled.")

        # 8. 合并 System Prompt
        final_system_prompt = self._system_prompt_override if self._system_prompt_override is not None else base_system_prompt
        if extended_prompt:
            final_system_prompt = final_system_prompt + "\n\n" + extended_prompt if final_system_prompt else extended_prompt

        # 9. 构建 MessageContext (委托给 ContextBuilder)
        max_context_messages = None
        if self._enable_max_context_messages:
            params = active_params
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}
            if params and isinstance(params, dict):
                max_context_messages = params.get("max_context_messages")

        context_builder = MessageContextBuilder(
            db=self.db,
            type_filter=self._type_filter,
            enable_cpl_filter=self._enable_cpl_filter,
            enable_image_with_model=self._enable_image_with_model,
            model_supports_images=self._model_supports_images(model),
            enable_zip_history=self._enable_zip_history,
            content_limit=self._content_limit,
            flatten_history=self._flatten_history,
            append_prompt=self._append_prompt,
            max_context_messages=max_context_messages,
            slice_range=self._slice_range,
            head_tail=self._head_tail
        )

        message_context = await context_builder.build(
            raw_history=materials.history,
            system_prompt=final_system_prompt
        )

        # 10. 组装并返回最终的 LLMInput
        return LLMInput(
            llm_config=llm_config,
            context=message_context,
            agent_config=agent_config
        )

    def get_providers(self) -> List[BaseToolProvider]:
        """供 Manager 调用以获取装配好的 Provider 实例"""
        return self._providers

    # ==================== 内部辅助方法 ====================

    async def _resolve_model(self, materials: GenerationMaterials) -> AIModel:
        model = None
        if self._global_model_keys:
            for key in self._global_model_keys:
                setting = materials.settings.get(key)
                if setting:
                    model = await provider_crud.get_model(self.db, model_id=setting)
                    if model:
                        break
            if not model:
                raise ValueError(f"未能从全局设置 {self._global_model_keys} 中找到有效的模型配置")
        else:
            is_agent_mode = not self._force_normal_mode and \
                            (materials.chat.chatMode == ChatMode.AGENT.value and materials.agent is not None)

            if is_agent_mode and materials.agent.aiModelId:
                model = await provider_crud.get_model(self.db, model_id=materials.agent.aiModelId)
                if not model:
                    raise ValueError(f"Agent 绑定的模型 {materials.agent.aiModelId} 不存在")
            else:
                if not materials.chat.ai_model:
                    raise ValueError("会话未配置模型")
                model = materials.chat.ai_model
        return model

    def _map_parameters(self, model_params_data: Any) -> Dict[str, Any]:
        """将扁平的数据库参数映射为结构化的 API 参数"""
        flat_params = {}
        if model_params_data:
            flat_params = json.loads(model_params_data) if isinstance(model_params_data, str) else model_params_data

        structured = {}
        param_def_map = {p.key: p for p in SUPPORTED_LLM_PARAMETERS}

        for key, value in flat_params.items():
            if key in ["max_context_messages", "stream", "enabled_mcp_ids", "enable_suggest"]:
                continue

            definition = param_def_map.get(key)
            if definition:
                target = structured
                for part in definition.path[:-1]:
                    target = target.setdefault(part, {})
                target[definition.path[-1]] = value

        if 'stream' in flat_params:
            structured['stream'] = flat_params['stream']

        return structured

    def _model_supports_images(self, model: AIModel) -> bool:
        meta = model.meta_config
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return False

        if not meta:
            return False

        input_modalities = []
        if isinstance(meta, dict):
            input_modalities = meta.get('input_modalities')
        elif hasattr(meta, 'input_modalities'):
            input_modalities = meta.input_modalities

        return 'image' in (input_modalities or [])

    def _extract_resume_payload(self, target_msg: Optional[Any]) -> Optional[Dict[str, Any]]:
        """从被截断的目标消息中提取 HITL 恢复所需的决策载荷"""
        if not (self._cutoff_message_id and self._enable_tools and target_msg):
            return None

        if target_msg.role != schemas_enums.MessageRole.ASSISTANT.value:
            return None

        decided_reviews = []
        for sub in target_msg.sub_messages:
            if sub.type == schemas_enums.SubMessageType.REVIEW_TOOL.value:
                try:
                    content = ReviewToolContent.from_json_string(sub.content)
                    if content.decision is not None:
                        decided_reviews.append((sub.createdAt, content))
                except (ValueError, ImportError):
                    pass

        if not decided_reviews:
            return None

        decided_reviews.sort(key=lambda x: x[0], reverse=True)
        latest_batch_id = decided_reviews[0][1].batch_id

        latest_batch_decisions = [item[1] for item in decided_reviews if item[1].batch_id == latest_batch_id]
        latest_batch_decisions.sort(key=lambda x: x.interrupt_index)

        resume_decisions = []
        for item in latest_batch_decisions:
            decision_dict = {"type": item.decision.type.value}
            if item.decision.type.value == "edit" and item.decision.edited_action:
                decision_dict["edited_action"] = item.decision.edited_action.model_dump()
            if item.decision.type.value == "reject":
                raw_reason = item.decision.message or ""
                injected_message = f"{item.tool_call_id} 本批次 调用工具:{item.name}拒绝执行; 拒绝理由 {raw_reason}"
                decision_dict["message"] = injected_message
            resume_decisions.append(decision_dict)

        return {"decisions": resume_decisions}
