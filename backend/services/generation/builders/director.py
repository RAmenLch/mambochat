# backend/services/generation/builders/director.py

import json
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.crud import provider_crud, checkpoint_map_crud
from backend.schemas import enums as schemas_enums
from backend.schemas.enums import ChatMode, AgentTypeEnum
from backend.schemas.message import ReviewToolContent, McpToolContent, AskUserContent
from backend.models.provider_model import AIModel

try:
    from mambo_agents.middleware.security_review import INTERRUPT_SOURCE as _SECURITY_REVIEW_SOURCE
except ImportError:  # pragma: no cover - 兼容旧版 mambo_agents
    _SECURITY_REVIEW_SOURCE = "mambo_security_review"

from backend.services.generation.core.llm_io import LLMInput, ModelConfig, RunTimeConfig, MessageSchema
from backend.services.generation.builders.material_loader import GenerationMaterialLoader, GenerationMaterials
from backend.services.generation.builders.param_utils import map_model_parameters
from backend.services.generation.builders.context_builder import MessageContextBuilder
from backend.services.generation.builders.initializers.chat_react_initializer import ChatBasedReActInitializer
from backend.services.generation.builders.initializers.agent_react_initializer import AgentBasedReActInitializer
from backend.services.generation.builders.initializers.deep_agent_initializer import DeepAgentInitializer
from backend.services.generation.builders.initializers.mambo_agent_initializer import MamboAgentInitializer
from backend.schemas.enums import WebSearchMode
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

    async def _resolve_branch_checkpoint(
        self, target_msg_id: str, history: List[MessageSchema]
    ) -> Tuple[Optional[str], bool]:
        """确定分支起点的 checkpoint_id。

        返回 (checkpoint_id, is_root):is_root 为 True 表示分支点是 thread 根
        checkpoint(首条消息重新生成的兜底)。

        优先级:
        1. target 自身映射(assistant 消息 retry 恢复用);
        2. 沿 parentId 链向上查找映射(重新回答命中用户消息/上一轮 assistant 的映射);
        3. 兜底:首条消息重新生成(链上无 assistant 祖先且无任何映射)时,
           取 thread 根 checkpoint —— 根在首个 assistant 轮之前,
           goal 等中间件状态为初始值,时间旅行语义正确。
        """
        # 1. 查自身
        cp = await checkpoint_map_crud.get_checkpoint_id(self.db, target_msg_id)
        if cp:
            return cp, False

        # 2. 沿 parentId 链向上查找;同时记录链上是否出现 assistant 祖先(兜底判定用)
        history_map: dict = {m.id: m for m in history if m.id}
        current_id: str = target_msg_id
        saw_assistant_ancestor = False
        while True:
            msg = history_map.get(current_id)
            if not msg:
                from backend.crud import message_crud
                db_msg = await message_crud.get_message(self.db, current_id)
                if not db_msg or not db_msg.parentId:
                    break
                if (
                    current_id != target_msg_id
                    and db_msg.role == schemas_enums.MessageRole.ASSISTANT.value
                ):
                    saw_assistant_ancestor = True
                current_id = db_msg.parentId
                continue
            if not msg.parentId:
                break
            parent_id = msg.parentId
            cp = await checkpoint_map_crud.get_checkpoint_id(self.db, parent_id)
            if cp:
                return cp, False
            parent_msg = history_map.get(parent_id)
            if (
                parent_msg
                and parent_msg.role == schemas_enums.MessageRole.ASSISTANT.value
            ):
                saw_assistant_ancestor = True
            current_id = parent_id

        # 3. 兜底:链上无 assistant 祖先,说明目标消息是首条用户消息的直接回复,
        #    以 thread 根 checkpoint 为分支点(goal 必为初始值);根不存在时维持
        #    原有行为(回退最新 checkpoint)
        if not saw_assistant_ancestor:
            from backend.checkpointer import aget_root_checkpoint_id
            root_cp = await aget_root_checkpoint_id(self.chat_id)
            if root_cp:
                return root_cp, True
        return None, False

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
        global_default_timeout = int(materials.settings.get("default_timeout", 60))
        model_max_retries = 0
        model_timeout = None
        model_stream_chunk_timeout = None
        model_context_length: Optional[int] = None
        if model.meta_config:
            try:
                meta = json.loads(model.meta_config) if isinstance(model.meta_config, str) else model.meta_config
                model_max_retries = int(meta.get("max_retries", 0))
                raw_timeout = meta.get("timeout")
                model_timeout = int(raw_timeout) if raw_timeout is not None else None
                raw_stream_chunk_timeout = meta.get("stream_chunk_timeout")
                if raw_stream_chunk_timeout is not None:
                    model_stream_chunk_timeout = float(raw_stream_chunk_timeout)
                raw_context_length = meta.get("context_length")
                if raw_context_length is not None:
                    model_context_length = int(raw_context_length)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        max_retries = model_max_retries if model_max_retries > 0 else global_max_retries
        timeout = model_timeout if model_timeout is not None else global_default_timeout

        llm_config = ModelConfig(
            model_id=model.modelId,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            parameters=api_params,
            max_retries=max_retries,
            timeout=timeout,
            context_length=model_context_length,
            stream_chunk_timeout=model_stream_chunk_timeout
        )

        resume_payload = self._extract_resume_payload(materials.target_msg)

        # 解析 chat 级别的 web_search_mode（未设置时回退到全局默认）
        ws_mode: Optional[WebSearchMode] = None
        raw_ws = materials.chat.web_search_mode
        if raw_ws:
            try:
                ws_mode = WebSearchMode(raw_ws)
            except ValueError:
                ws_mode = None
        else:
            raw_default_ws = materials.settings.get("web_search_default_mode")
            if raw_default_ws:
                try:
                    ws_mode = WebSearchMode(raw_default_ws)
                except ValueError:
                    ws_mode = None

        # 网页搜索是否走全局代理
        ws_proxy_url = None
        if (
            materials.settings.get("web_search_use_proxy") == "True"
            and materials.settings.get("proxy_enabled") == "True"
        ):
            ws_proxy_url = materials.settings.get("proxy_url")

        if is_agent_mode:
            agent_type_str = materials.agent.AgentType
            if hasattr(agent_type_str, 'value'):
                agent_type_str = agent_type_str.value

            if agent_type_str == AgentTypeEnum.MAMBO.value:
                initializer = MamboAgentInitializer(
                    db=self.db,
                    agent=materials.agent,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools,
                    web_search_mode=ws_mode,
                    web_search_proxy_url=ws_proxy_url,
                )
            elif agent_type_str == AgentTypeEnum.DEEP.value:
                initializer = DeepAgentInitializer(
                    db=self.db,
                    agent=materials.agent,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools,
                    web_search_mode=ws_mode,
                    web_search_proxy_url=ws_proxy_url,
                )
            else:
                initializer = AgentBasedReActInitializer(
                    db=self.db,
                    agent=materials.agent,
                    resume_payload=resume_payload,
                    enable_tools=self._enable_tools,
                    enable_resource_merge=self._enable_resource_merge,
                    external_tools=self._tools,
                    web_search_mode=ws_mode,
                    web_search_proxy_url=ws_proxy_url,
                )
            base_system_prompt = materials.agent.systemPrompt or ""
        else:
            initializer = ChatBasedReActInitializer(
                db=self.db,
                chat=materials.chat,
                resume_payload=resume_payload,
                enable_tools=self._enable_tools,
                enable_resource_merge=self._enable_resource_merge,
                external_tools=self._tools,
                web_search_mode=ws_mode,
                web_search_proxy_url=ws_proxy_url,
            )
            base_system_prompt = materials.chat.systemPrompt or ""

        agent_config, extended_prompt = await initializer.initialize()

        agent_config.llm_config = llm_config
        agent_config.main_model_input_modalities = self._resolve_input_modalities(model)

        # 向没有自己模型的子 agent 继承父 agent 的 llm_config
        if agent_config.sub_configs:
            for sub in agent_config.sub_configs:
                if sub.llm_config is None:
                    sub.llm_config = llm_config
                    sub.main_model_input_modalities = agent_config.main_model_input_modalities

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
            head_tail=self._head_tail,
            language=materials.settings.get("language")
        )

        # DeepSeek 等需要回传 reasoning_content 的模型，将 REASONING 加入 type_filter
        # 使其走正常的 type_filter + CPL 流程，由转换层映射到独立的 reasoning_content 字段
        if provider.worker_type == schemas_enums.ProviderWorkerType.DEEPSEEK.value and self._type_filter:
            context_builder.type_filter = self._type_filter | {schemas_enums.SubMessageType.REASONING.value}

        message_context = await context_builder.build(
            raw_history=materials.history,
            system_prompt=final_system_prompt
        )

        # 确定分支 checkpoint（用于 LangGraph 时间旅行，沿 parentId 链查找）
        branch_checkpoint_id: Optional[str] = None
        branch_from_root = False
        if self._cutoff_message_id and materials.target_msg:
            branch_checkpoint_id, branch_from_root = await self._resolve_branch_checkpoint(
                self._cutoff_message_id, materials.history
            )

        rt_config = RunTimeConfig(
            chat_id=self.chat_id,
            message_id=self._cutoff_message_id,
            manager_name=self._manager_name,
            branch_checkpoint_id=branch_checkpoint_id,
            branch_from_root=branch_from_root,
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

    def _resolve_input_modalities(self, model: AIModel) -> List[str]:
        """返回模型声明的多模态输入类型（block type 维度）。

        能力未声明时视为纯文本模型，返回空列表。``document`` 归一化为 ``file``。
        """
        meta = self._parse_meta_config(model)
        if not meta:
            return []
        raw = meta.get('input_modalities') or []
        return sorted({('file' if m == 'document' else m) for m in raw})

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

        # 2. 提取所有 AskUser 回答（当前批次的）
        decided_ask_users: List[Tuple[Any, AskUserContent]] = []
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

        # 3. 构建 ReviewTool 恢复载荷（优先使用 {interrupt_id: payload} 地图格式）
        review_payload = None
        if decided_reviews:
            decided_reviews.sort(key=lambda x: x[0], reverse=True)
            latest_review_batch_id = decided_reviews[0][1].batch_id
            latest_batch_decisions = [item[1] for item in decided_reviews if item[1].batch_id == latest_review_batch_id]
            latest_batch_decisions.sort(key=lambda x: x.interrupt_index)

            # 按 interrupt_id 分组，同时检测是否所有项都有 interrupt_id
            by_interrupt: Dict[str, list] = {}
            all_have_ids = True
            for item in latest_batch_decisions:
                iid = item.interrupt_id
                if iid:
                    by_interrupt.setdefault(iid, []).append(item)
                else:
                    all_have_ids = False
                    break

            if all_have_ids and by_interrupt:
                review_payload = {}
                for iid, items in by_interrupt.items():
                    decisions = []
                    for item in items:
                        decision_dict = {
                            "type": item.decision.type.value,
                            "tool_call_id": item.tool_call_id,
                        }
                        if item.decision.type.value == "edit" and item.decision.edited_action:
                            decision_dict["edited_action"] = item.decision.edited_action.model_dump()
                        if item.decision.type.value == "reject":
                            raw_reason = item.decision.message or ""
                            injected_message = f"{item.tool_call_id} 本批次 调用工具:{item.name}拒绝执行; 拒绝理由 {raw_reason}"
                            decision_dict["message"] = injected_message
                        decisions.append(decision_dict)
                    review_payload[iid] = {
                        "source": _SECURITY_REVIEW_SOURCE,
                        "decisions": decisions,
                    }
            else:
                # 回退：旧数据无 interrupt_id，使用单值格式
                resume_decisions = []
                for item in latest_batch_decisions:
                    decision_dict = {
                        "type": item.decision.type.value,
                        "tool_call_id": item.tool_call_id,
                    }
                    if item.decision.type.value == "edit" and item.decision.edited_action:
                        decision_dict["edited_action"] = item.decision.edited_action.model_dump()
                    if item.decision.type.value == "reject":
                        raw_reason = item.decision.message or ""
                        injected_message = f"{item.tool_call_id} 本批次 调用工具:{item.name}拒绝执行; 拒绝理由 {raw_reason}"
                        decision_dict["message"] = injected_message
                    resume_decisions.append(decision_dict)
                review_payload = {
                    "source": _SECURITY_REVIEW_SOURCE,
                    "decisions": resume_decisions,
                }

        # 4. 构建 AskUser 恢复载荷（始终优先使用 {interrupt_id: payload} 地图格式）
        ask_user_payload = None
        if decided_ask_users:
            decided_ask_users.sort(key=lambda x: x[0], reverse=True)
            latest_ask_user = decided_ask_users[0][1]
            latest_batch_id = latest_ask_user.batch_id

            same_batch = [
                item[1] for item in decided_ask_users
                if item[1].batch_id == latest_batch_id
            ]
            same_batch.sort(key=lambda x: x.interrupt_index)

            # 尝试构建 {interrupt_id: payload} 地图
            ask_user_payload = {}
            all_have_ids = True
            for item in same_batch:
                if item.interrupt_id:
                    ask_user_payload[item.interrupt_id] = {
                        "status": item.ask_status or "answered",
                        "answers": item.answers,
                    }
                else:
                    all_have_ids = False
                    break

            if not all_have_ids:
                # 回退：旧数据无 interrupt_id，使用单值格式
                ask_user_payload = {
                    "status": latest_ask_user.ask_status or "answered",
                    "answers": latest_ask_user.answers,
                }

        # 5. 合并恢复载荷（同时存在 ReviewTool 和 AskUser 时合并两者的 interrupt 地图）
        return self._merge_resume_payloads(
            ask_user_payload, review_payload,
            decided_ask_users, decided_reviews,
        )

    @staticmethod
    def _is_resume_map(payload: Optional[Dict[str, Any]]) -> bool:
        """Check if payload is a resume map ({interrupt_id: payload}) vs plain dict."""
        if not isinstance(payload, dict) or not payload:
            return False
        return all(
            isinstance(k, str) and len(k) == 32 and all(c in "0123456789abcdef" for c in k)
            for k in payload
        )

    @staticmethod
    def _merge_resume_payloads(
        ask_user_payload: Optional[Dict[str, Any]],
        review_payload: Optional[Dict[str, Any]],
        decided_ask_users: list,
        decided_reviews: list,
    ) -> Optional[Dict[str, Any]]:
        """Merge ask_user and review_tool resume payloads.

        When both are resume maps ({interrupt_id: ...}), merge them.
        When only one is a map, return the map.
        When neither is a map (old data), return the latest by time.
        """
        ask_is_map = LLMInputDirector._is_resume_map(ask_user_payload)
        review_is_map = LLMInputDirector._is_resume_map(review_payload)

        if ask_is_map and review_is_map:
            return {**review_payload, **ask_user_payload}
        if ask_is_map:
            return ask_user_payload
        if review_is_map:
            return review_payload
        if ask_user_payload is not None and review_payload is not None:
            all_decided = decided_reviews + [(item[0], item[1]) for item in decided_ask_users]
            all_decided.sort(key=lambda x: x[0], reverse=True)
            latest_type = all_decided[0][1]
            if isinstance(latest_type, AskUserContent):
                return ask_user_payload
            else:
                return review_payload
        return ask_user_payload or review_payload
