# backend/services/generation/builders/director.py

import json
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.crud import provider_crud
from backend.schemas import enums as schemas_enums
from backend.schemas.enums import ChatMode, AgentTypeEnum
from backend.schemas.message import ReviewToolContent, McpToolContent, AskUserContent
from backend.models.provider_model import AIModel

from backend.services.generation.core.llm_io import LLMInput, ModelConfig, RunTimeConfig, MessageSchema
from backend.services.generation.builders.material_loader import GenerationMaterialLoader, GenerationMaterials
from backend.services.generation.builders.param_utils import map_model_parameters
from backend.services.generation.builders.context_builder import MessageContextBuilder
from backend.services.generation.builders.initializers.chat_react_initializer import ChatBasedReActInitializer
from backend.services.generation.builders.initializers.agent_react_initializer import AgentBasedReActInitializer
from backend.services.generation.builders.initializers.deep_agent_initializer import DeepAgentInitializer
from backend.services.generation.tools.base_tool_provider import BaseToolProvider


class LLMInputDirector:
    def __init__(self, db: AsyncSession, chat_id: str):
        if not chat_id:
            raise ValueError("LLMInputDirector requires a chat_id")

        self.db = db
        self.chat_id = chat_id
        self._manager_name: Optional[str] = None

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
        self._history_override: Optional[List[MessageSchema]] = None
        self._enable_resource_merge: bool = False
        self._content_limit: Optional[int] = None
        self._flatten_history: bool = False
        self._append_prompt: Optional[str] = None
        self._tools: Optional[List[BaseTool]] = None
        self._enable_max_context_messages: bool = False
        self._enable_tools: bool = False

        self._force_normal_mode: bool = False

        self._providers: List[BaseToolProvider] = []

    def set_manager_name(self, name):
        self._manager_name = name
        return self

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

    def set_history_override(self, history: List[MessageSchema]) -> "LLMInputDirector":
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
        self._force_normal_mode = True
        return self

    async def build(self) -> LLMInput:
        materials = await GenerationMaterialLoader.load(
            db=self.db,
            chat_id=self.chat_id,
            cutoff_message_id=self._cutoff_message_id,
            cutoff_include=self._cutoff_include,
            history_override=self._history_override
        )

        model = await self._resolve_model(materials)
        provider = model.provider
        if not provider:
            raise ValueError(f"Model {model.modelId} has no associated provider")

        is_agent_mode = not self._force_normal_mode and \
                        (materials.chat.chatMode == ChatMode.AGENT.value and materials.agent is not None)

        active_params = (materials.agent.parsed_model_parameters if is_agent_mode
                         else materials.chat.parsed_model_parameters)

        api_params = {}
        if not self._global_model_keys:
            api_params = map_model_parameters(active_params)

        api_params["_worker_type"] = provider.worker_type

        proxy_url = None
        if provider.use_proxy and materials.settings.get("proxy_enabled") == "True":
            proxy_url = materials.settings.get("proxy_url")

        global_max_retries = int(materials.settings.get("default_max_retries", 3))
        model_max_retries = 0
        if model.meta_config:
            try:
                meta = json.loads(model.meta_config) if isinstance(model.meta_config, str) else model.meta_config
                model_max_retries = int(meta.get("max_retries", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        max_retries = model_max_retries if model_max_retries > 0 else global_max_retries

        llm_config = ModelConfig(
            model_id=model.modelId,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            parameters=api_params,
            max_retries=max_retries
        )

        resume_payload = self._extract_resume_payload(materials.target_msg)

        if is_agent_mode:
            if materials.agent.AgentType == AgentTypeEnum.DEEP.value or materials.agent.AgentType == AgentTypeEnum.DEEP:
                initializer = DeepAgentInitializer(
                    db=self.db,
                    agent=materials.agent,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools
                )
            else:
                initializer = AgentBasedReActInitializer(
                    db=self.db,
                    agent=materials.agent,
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
                resume_payload=resume_payload,
                enable_tools=self._enable_tools,
                enable_resource_merge=self._enable_resource_merge,
                external_tools=self._tools
            )
            base_system_prompt = materials.chat.systemPrompt or ""

        agent_config, extended_prompt = await initializer.initialize()

        agent_config.llm_config = llm_config

        self._providers = initializer.get_providers()

        if self._cutoff_message_id and materials.target_msg:
            for sub in materials.target_msg.sub_messages:
                if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                    if sub.status in [schemas_enums.MessageStatus.GENERATING.value, schemas_enums.MessageStatus.PENDING_REVIEW.value, schemas_enums.MessageStatus.FAILED.value]:
                        try:
                            content_obj = McpToolContent.from_json_string(sub.content)
                            if content_obj and content_obj.tool_call_id:
                                for tp in self._providers:
                                    if tp.matches_tool_name(content_obj.name):
                                        tp.restore_state(content_obj.tool_call_id, sub.id, content_obj)
                                        break
                        except (ValueError, TypeError, ImportError):
                            pass

        if not self._cutoff_message_id and agent_config.hitl_interrupt_on:
            raise ValueError("Build failed: assistant_message_id is required when HITL is enabled.")

        final_system_prompt = self._system_prompt_override if self._system_prompt_override is not None else base_system_prompt
        if extended_prompt:
            final_system_prompt = final_system_prompt + "\n\n" + extended_prompt if final_system_prompt else extended_prompt

        max_context_messages = None
        if self._enable_max_context_messages:
            max_context_messages = active_params.get("max_context_messages")

        context_builder = MessageContextBuilder(
            db=self.db,
            type_filter=self._type_filter,
            enable_cpl_filter=self._enable_cpl_filter,
            enable_image_with_model=self._enable_image_with_model,
            model_supports_images=self._model_supports_images(model),
            model_supports_audio=self._model_supports_audio(model),
            model_supports_video=self._model_supports_video(model),
            model_supports_file=self._model_supports_file(model),
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

        rt_config = RunTimeConfig(
            chat_id=self.chat_id,
            message_id=self._cutoff_message_id,
            manager_name=self._manager_name
        )

        return LLMInput(
            context=message_context,
            agent_config=agent_config,
            run_time_config=rt_config
        )

    def get_providers(self) -> List[BaseToolProvider]:
        return self._providers

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

    def _parse_meta_config(self, model: AIModel) -> Optional[dict]:
        """解析模型的 meta_config 为字典。解析失败返回 None。"""
        meta = model.meta_config
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return None
        if not meta or not isinstance(meta, dict):
            return None
        return meta

    def _model_supports_images(self, model: AIModel) -> bool:
        meta = self._parse_meta_config(model)
        if not meta:
            return False
        return 'image' in (meta.get('input_modalities') or [])

    def _model_supports_audio(self, model: AIModel) -> bool:
        meta = self._parse_meta_config(model)
        if not meta:
            return False
        return 'audio' in (meta.get('input_modalities') or [])

    def _model_supports_video(self, model: AIModel) -> bool:
        meta = self._parse_meta_config(model)
        if not meta:
            return False
        return 'video' in (meta.get('input_modalities') or [])

    def _model_supports_file(self, model: AIModel) -> bool:
        """检测模型是否支持文件输入(PDF等)"""
        meta = self._parse_meta_config(model)
        if not meta:
            return False
        input_modalities = meta.get('input_modalities') or []
        return 'file' in input_modalities or 'document' in input_modalities

    def _extract_resume_payload(self, target_msg: Optional[MessageSchema]) -> Optional[Dict[str, Any]]:
        if not (self._cutoff_message_id and self._enable_tools and target_msg):
            return None

        if target_msg.role != schemas_enums.MessageRole.ASSISTANT.value:
            return None

        # 1. 提取 ReviewTool 决策
        decided_reviews = []
        for sub in target_msg.sub_messages:
            if sub.type == schemas_enums.SubMessageType.REVIEW_TOOL.value:
                try:
                    content = ReviewToolContent.from_json_string(sub.content)
                    if content.decision is not None:
                        decided_reviews.append((sub.createdAt, content))
                except (ValueError, ImportError):
                    pass

        # 2. 提取 AskUser 回答
        decided_ask_users = []
        for sub in target_msg.sub_messages:
            if sub.type == schemas_enums.SubMessageType.ASK_USER.value:
                try:
                    content = AskUserContent.from_json_string(sub.content)
                    if content.answers is not None:
                        decided_ask_users.append((sub.createdAt, content))
                except (ValueError, ImportError):
                    pass

        if not decided_reviews and not decided_ask_users:
            return None

        # 3. 构建 ReviewTool 恢复载荷
        resume_decisions = []
        if decided_reviews:
            decided_reviews.sort(key=lambda x: x[0], reverse=True)
            latest_review_batch_id = decided_reviews[0][1].batch_id
            latest_batch_decisions = [item[1] for item in decided_reviews if item[1].batch_id == latest_review_batch_id]
            latest_batch_decisions.sort(key=lambda x: x.interrupt_index)

            for item in latest_batch_decisions:
                decision_dict = {"type": item.decision.type.value}
                if item.decision.type.value == "edit" and item.decision.edited_action:
                    decision_dict["edited_action"] = item.decision.edited_action.model_dump()
                if item.decision.type.value == "reject":
                    raw_reason = item.decision.message or ""
                    injected_message = f"{item.tool_call_id} 本批次 调用工具:{item.name}拒绝执行; 拒绝理由 {raw_reason}"
                    decision_dict["message"] = injected_message
                resume_decisions.append(decision_dict)

        # 4. 构建 AskUser 恢复载荷
        ask_user_payload = None
        if decided_ask_users:
            decided_ask_users.sort(key=lambda x: x[0], reverse=True)
            latest_ask_user = decided_ask_users[0][1]
            ask_user_payload = {
                "status": latest_ask_user.ask_status or "answered",
                "answers": latest_ask_user.answers,
            }

        # 5. 组合恢复载荷
        # 如果同时存在 ReviewTool 和 AskUser，只返回后触发的那个（按时间排序取最新）
        all_decided = decided_reviews + decided_ask_users
        all_decided.sort(key=lambda x: x[0], reverse=True)
        latest_type = all_decided[0][1]

        if isinstance(latest_type, AskUserContent):
            return ask_user_payload
        else:
            return {"decisions": resume_decisions}
