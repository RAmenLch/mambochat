# backend/services/generation/llm_input_builder.py

import json
import base64
from datetime import datetime as dt
from typing import List, Dict, Any, Optional, Set, Tuple
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.crud import chat_crud, message_crud, setting_crud, provider_crud, resource_crud, mcp_crud
from backend.services.file_service import FileService
from backend.schemas import enums as schemas_enums, AIModel
from backend.schemas.message import McpToolContent, ReviewToolContent
from backend.services.generation.llm_io import LLMInput
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS
from backend.services.generation.resource_dispatcher import ResourceDispatcher
from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mcp_tool_provider import MCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider
from backend.services.generation.tools.kb_tool_provider import KBToolProvider

# 以 application/* 开头但本质是文本的 MIME 类型
_KNOWN_TEXT_APPLICATION_TYPES = {
    "application/json", "application/xml", "application/sql",
    "application/javascript", "application/x-sh", "application/x-yaml",
    "application/rtf", "application/x-ipynb+json",
}


def _is_text_mime_type(mime_type: str) -> bool:
    if mime_type.startswith("text/"):
        return True
    return mime_type in _KNOWN_TEXT_APPLICATION_TYPES


class LLMInputBuilder:
    """
    LLM 输入构建器。
    负责从数据库或内存加载素材（Chat, Provider, Settings, Messages），
    并根据配置执行过滤、切片、多模态转换，最终生成标准化的 LLMInput 对象。

    多轮拆分：
    对于 Assistant 消息，按时间顺序遍历所有子消息（包括被内容过滤的 Reasoning），
    以 McpTool 后出现的任意非 McpTool 子消息作为轮次分界线，自动拆分为
    多个 assistant→tool 消息序列。边界检测与内容过滤完全解耦。
    """

    def __init__(self, db: AsyncSession, chat_id: str):
        if not chat_id:
            raise ValueError("LLMInputBuilder requires a chat_id")

        self.db = db
        self.chat_id = chat_id

        # 配置项
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

        # 内部数据缓存
        self._cached_chat = None
        self._cached_settings = None
        self._cached_model = None
        self._file_content_cache: Dict[str, Dict[str, Any]] = {}

        # 运行时数据
        self.chat = None
        self.history = []
        self.settings = {}
        self._target_msg = None

        self.providers: List[BaseToolProvider] = []
        self._hitl_interrupt_on: Dict[str, bool] = {}

    # --- 配置方法 (Fluent API) ---

    def slice_until_message(self, message_id: str, include_target: bool = False) -> "LLMInputBuilder":
        self._cutoff_message_id = message_id
        self._cutoff_include = include_target
        return self

    def slice(self, start: int, end: Optional[int] = None) -> "LLMInputBuilder":
        self._slice_range = slice(start, end)
        return self

    def slice_head_tail(self, head: int, tail: int) -> "LLMInputBuilder":
        self._head_tail = (head, tail)
        return self

    def filter_sub_message_types(self, *types: str) -> "LLMInputBuilder":
        self._type_filter = set(types)
        return self

    def enable_cpl_filter(self) -> "LLMInputBuilder":
        self._enable_cpl_filter = True
        return self

    def enable_image_with_model(self) -> "LLMInputBuilder":
        self._enable_image_with_model = True
        return self

    def disable_zip_history(self) -> "LLMInputBuilder":
        self._enable_zip_history = False
        return self

    def use_global_model(self, setting_keys: List[str]) -> "LLMInputBuilder":
        self._global_model_keys = setting_keys
        return self

    def set_system_prompt(self, prompt: str) -> "LLMInputBuilder":
        self._system_prompt_override = prompt
        return self

    def set_history_override(self, history: List[Any]) -> "LLMInputBuilder":
        self._history_override = history
        return self

    def enable_resource_prompt_merge(self) -> "LLMInputBuilder":
        self._enable_resource_merge = True
        return self

    def limit_sub_message_content(self, max_length: int) -> "LLMInputBuilder":
        self._content_limit = max_length
        return self

    def flatten_history_to_single_user_message(self) -> "LLMInputBuilder":
        self._flatten_history = True
        return self

    def append_user_message(self, content: str) -> "LLMInputBuilder":
        self._append_prompt = content
        return self

    def set_tools(self, tools: List[BaseTool]) -> "LLMInputBuilder":
        self._tools = tools
        return self

    def enable_max_context_messages(self) -> "LLMInputBuilder":
        self._enable_max_context_messages = True
        return self

    def enable_tools(self) -> "LLMInputBuilder":
        self._enable_tools = True
        return self

    # --- 核心构建方法 ---

    async def build(self) -> LLMInput:
        await self._load_materials()

        model = await self._resolve_model()
        provider = model.provider

        system_prompt = self._system_prompt_override
        if system_prompt is None:
            system_prompt = self.chat.systemPrompt or ""

        extended_prompt = await self._setup_providers_and_resources()
        if extended_prompt:
            system_prompt = system_prompt + "\n\n" + extended_prompt if system_prompt else extended_prompt

        effective_history = self.history
        if self._enable_zip_history:
            effective_history = await self._apply_zip_history_logic(effective_history)

        effective_history = self._apply_slicing(effective_history)

        if self._enable_max_context_messages:
            effective_history = self._apply_max_context_limit(effective_history)

        messages_payload = await self._build_payload(effective_history)

        if system_prompt:
            messages_payload.insert(0, {"role": "system", "content": system_prompt})

        api_params = {}
        if not self._global_model_keys:
            api_params = self._map_parameters(self.chat.modelParameters)

        proxy_url = None
        if provider.use_proxy and self.settings.get("proxy_enabled") == "True":
            proxy_url = self.settings.get("proxy_url")

        resume_payload = None
        if self._cutoff_message_id:
            target_msg = self._target_msg
            if not target_msg:
                target_msg = await message_crud.get_message(self.db, message_id=self._cutoff_message_id)

            if target_msg and target_msg.role == schemas_enums.MessageRole.ASSISTANT.value:
                decided_reviews = []
                for sub in target_msg.sub_messages:
                    if sub.type == schemas_enums.SubMessageType.REVIEW_TOOL.value:
                        try:
                            content = ReviewToolContent.from_json_string(sub.content)
                            if content.decision is not None:
                                decided_reviews.append((sub.createdAt, content))
                        except (ValueError, ImportError):
                            pass

                if decided_reviews:
                    decided_reviews.sort(key=lambda x: x[0], reverse=True)
                    latest_batch_id = decided_reviews[0][1].batch_id

                    latest_batch_decisions = [item[1] for item in decided_reviews if
                                              item[1].batch_id == latest_batch_id]
                    latest_batch_decisions.sort(key=lambda x: x.interrupt_index)

                    resume_decisions = []
                    for item in latest_batch_decisions:
                        decision_dict = {"type": item.decision.type.value}
                        if item.decision.type.value == "edit" and item.decision.edited_action:
                            decision_dict["edited_action"] = item.decision.edited_action.model_dump()
                        if item.decision.type.value == "reject":
                            raw_reason = item.decision.message or ""
                            injected_message = (
                                f"{item.tool_call_id} 本批次 调用工具:{item.name}拒绝执行; "
                                f"拒绝理由 {raw_reason}"
                            )
                            decision_dict["message"] = injected_message
                        resume_decisions.append(decision_dict)

                    resume_payload = {"decisions": resume_decisions}

        if not self._cutoff_message_id and self._hitl_interrupt_on:
            raise ValueError(
                "Build failed: assistant_message_id (_cutoff_message_id) is required when HITL is enabled.")

        return LLMInput(
            model_id=model.modelId,
            messages=messages_payload,
            parameters=api_params,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            tools=self._tools,
            tool_choice=None,
            hitl_interrupt_on=self._hitl_interrupt_on,
            thread_id=self._cutoff_message_id or self.chat_id,
            resume_payload=resume_payload
        )

    # --- 内部处理逻辑 ---

    async def _load_materials(self):
        if not self._cached_chat:
            self.chat = await chat_crud.get_chat(self.db, self.chat_id)
            if not self.chat:
                raise ValueError(f"Chat {self.chat_id} not found.")
            self._cached_chat = self.chat
        else:
            self.chat = self._cached_chat

        if self._history_override is not None:
            self.history = self._history_override
            if self._cutoff_message_id:
                self._target_msg = next(
                    (m for m in self.history if getattr(m, 'id', None) == self._cutoff_message_id), None)
        else:
            all_msgs = await message_crud.get_messages_by_chat(self.db, self.chat_id)
            if self._cutoff_message_id:
                try:
                    idx = next(i for i, m in enumerate(all_msgs) if m.id == self._cutoff_message_id)
                    self._target_msg = all_msgs[idx]
                    end_index = idx + 1 if self._cutoff_include else idx
                    self.history = all_msgs[:end_index]
                except StopIteration:
                    self.history = all_msgs
            else:
                self.history = all_msgs

        if not self._cached_settings:
            all_settings = await setting_crud.get_all_settings(self.db)
            self.settings = {s.key: s.value for s in all_settings}
            self._cached_settings = self.settings
        else:
            self.settings = self._cached_settings

    async def _resolve_model(self) -> "AIModel":
        if self._cached_model:
            return self._cached_model

        model = None
        if self._global_model_keys:
            for key in self._global_model_keys:
                setting = self.settings.get(key)
                if setting:
                    model_id = setting
                    model = await provider_crud.get_model(self.db, model_id=model_id)
                    if model:
                        break
            if not model:
                raise ValueError(f"未能从全局设置 {self._global_model_keys} 中找到有效的模型配置")
        else:
            if not self.chat.ai_model:
                raise ValueError("会话未配置模型")
            model = self.chat.ai_model

        self._cached_model = model
        return model

    async def _setup_providers_and_resources(self) -> str:
        self.providers = []
        extended_prompts = []

        knowledge_bases = []
        if self._enable_resource_merge and self.chat.resource_prompt_list:
            dispatcher = ResourceDispatcher(self.db)
            dispatch_result = await dispatcher.dispatch(self.chat.resource_prompt_list)

            for content in dispatch_result["system_prompts"]:
                extended_prompts.append(content)
            for content in dispatch_result["submessage_templates"]:
                extended_prompts.append(content)

            knowledge_bases = dispatch_result["knowledge_bases"]

        if knowledge_bases:
            self.providers.append(KBToolProvider(self.db, knowledge_bases))

        if self._enable_tools:
            params = {}
            if self.chat and self.chat.modelParameters:
                try:
                    params = json.loads(self.chat.modelParameters) if isinstance(self.chat.modelParameters,
                                                                                 str) else self.chat.modelParameters
                except (json.JSONDecodeError, TypeError):
                    pass

            mcp_ids = self.chat.enabled_mcp_ids or []
            if mcp_ids:
                self.providers.append(MCPToolProvider(self.db, mcp_ids))

                mcp_tools = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                for tool in mcp_tools:
                    if tool.review_mode == schemas_enums.ToolReviewMode.REQUIRE_REVIEW.value:
                        self._hitl_interrupt_on[tool.name] = True

            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

        all_tools = []
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)

        if all_tools:
            if self._tools is None:
                self._tools = []
            self._tools.extend(all_tools)

        return "\n\n".join(extended_prompts) if extended_prompts else ""

    def _apply_slicing(self, history: List[Any]) -> List[Any]:
        if not history:
            return []

        if self._head_tail:
            head, tail = self._head_tail
            if len(history) <= (head + tail):
                return history
            return history[:head] + history[-tail:]

        if self._slice_range:
            return history[self._slice_range]

        return history

    def _apply_max_context_limit(self, history: List[Any]) -> List[Any]:
        if not history:
            return []

        params = self.chat.modelParameters
        if not params:
            return history

        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return history

        limit = params.get("max_context_messages")
        if not limit or not isinstance(limit, int):
            return history

        if limit % 2 != 0:
            limit += 1

        if len(history) <= 1:
            return history

        last_message = history[-1]
        history_context = history[:-1]

        if len(history_context) <= limit:
            return history

        sliced_context = history_context[-limit:]

        return sliced_context + [last_message]

    async def _apply_zip_history_logic(self, history: List[Any]) -> List[Any]:
        last_enabled_zip_index = -1
        zip_content = None

        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            for sub in msg.sub_messages:
                if sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
                    config = json.loads(sub.config) if isinstance(sub.config, str) else (sub.config or {})
                    if config.get('zip_enable') is True:
                        last_enabled_zip_index = i
                        zip_content = sub.content
                        break
            if last_enabled_zip_index != -1:
                break

        if last_enabled_zip_index != -1 and zip_content:
            user_msg = SimpleNamespace(
                role=schemas_enums.MessageRole.USER.value,
                sub_messages=[SimpleNamespace(content="对之前的对话进行了总结摘要。",
                                              type=schemas_enums.SubMessageType.NORMAL.value, config='{}')]
            )
            assistant_msg = SimpleNamespace(
                role=schemas_enums.MessageRole.ASSISTANT.value,
                sub_messages=[
                    SimpleNamespace(content=zip_content, type=schemas_enums.SubMessageType.NORMAL.value, config='{}')]
            )
            return [user_msg, assistant_msg] + history[last_enabled_zip_index + 1:]

        return history

    async def _build_payload(self, history: List[Any]) -> List[Dict[str, Any]]:
        """
        将消息对象列表转换为 LLM 字典列表。

        对 Assistant 消息使用多轮拆分逻辑 (_convert_assistant_to_rounds)，
        自动按 McpTool 子消息分界为多个 assistant→tool 消息序列，
        避免 LLM 将原本多轮进行的工具调用误解为单轮并发执行。
        """
        payload = []
        total_count = len(history)

        for i, msg in enumerate(history):
            recency_rank = total_count - i

            if msg.role == schemas_enums.MessageRole.ASSISTANT.value:
                round_messages = await self._convert_assistant_to_rounds(msg, recency_rank)
                payload.extend(round_messages)
            else:
                llm_msg = await self._convert_message_to_llm_dict(msg, recency_rank)
                if llm_msg:
                    payload.append(llm_msg)

        if self._flatten_history and payload:
            flattened_content = ""
            for msg in payload:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                raw_content = msg.get("content")

                content_str = ""
                if isinstance(raw_content, str):
                    content_str = raw_content
                elif isinstance(raw_content, list):
                    texts = [item["text"] for item in raw_content if item.get("type") == "text"]
                    content_str = "\n".join(texts)

                if content_str:
                    flattened_content += f"{role_label}: {content_str}\n\n"

            payload = [{"role": "user", "content": flattened_content.strip()}]

        if self._append_prompt:
            payload.append({"role": "user", "content": self._append_prompt})

        return self._merge_consecutive_roles(payload)

    # ==================== 核心改动区域 ====================

    async def _convert_assistant_to_rounds(self, msg: Any, recency_rank: int) -> List[Dict[str, Any]]:
        """
        将一个 Assistant 消息拆分为多轮 LLM 消息序列。

        核心设计：**边界检测与内容过滤完全解耦**。
        - 边界检测：遍历 ALL 子消息（包括被 CPL/类型过滤掉的 Reasoning 等），
          当 McpTool 之后出现任意非 McpTool 子消息时，视为新一轮 LLM 调用的开始。
        - 内容填充：仅将通过 _should_include_sub_message 的子消息纳入 payload。

        这保证了即使 Reasoning 触发了工具调用（Reasoning→Tool→Reasoning→Tool...），
        每个工具调用仍被正确拆分为独立的串行轮次，而非被合并为一次并发调用。

        不依赖子消息 ID 格式，保持版本稳定性。
        """
        # 按 createdAt 排序，保证时间顺序
        sorted_subs = sorted(
            msg.sub_messages,
            key=lambda s: (getattr(s, 'createdAt', None) or dt.min, getattr(s, 'sortOrder', 0))
        )

        rounds: List[Dict[str, List]] = []
        current_round: Dict[str, List] = {"content_parts": [], "tool_calls": [], "tool_results": []}
        seen_tool_in_round = False

        for sub in sorted_subs:
            is_mcp_tool = (sub.type == schemas_enums.SubMessageType.MCP_TOOL.value)

            if is_mcp_tool:
                # ── McpTool: 始终参与边界标记，仅在通过过滤时填充数据 ──
                seen_tool_in_round = True

                if self._should_include_sub_message(sub, recency_rank):
                    try:
                        tool_content = McpToolContent.from_json_string(sub.content)
                        current_round["tool_calls"].append(tool_content.to_openai_tool_call())
                        result_msg = tool_content.to_openai_tool_result_message()
                        if result_msg:
                            current_round["tool_results"].append(result_msg)
                    except (ValueError, TypeError):
                        continue
            else:
                # ── 非 McpTool: 任何此类子消息出现在工具之后即为新轮次起点 ──
                if seen_tool_in_round:
                    # 关闭当前轮次（仅当有实际内容时才入列）
                    if current_round["content_parts"] or current_round["tool_calls"]:
                        rounds.append(current_round)
                    current_round = {"content_parts": [], "tool_calls": [], "tool_results": []}
                    seen_tool_in_round = False

                # 内容填充：仅通过过滤的子消息才产出 payload
                if self._should_include_sub_message(sub, recency_rank):
                    part = await self._convert_sub_message_to_part(sub)
                    if part:
                        current_round["content_parts"].append(part)

        # 收集最后一轮
        if current_round["content_parts"] or current_round["tool_calls"]:
            rounds.append(current_round)

        # 转换为 LLM 字典序列
        result = []
        for round_data in rounds:
            assistant_msg: Dict[str, Any] = {"role": "assistant"}

            if round_data["content_parts"]:
                if len(round_data["content_parts"]) == 1 and round_data["content_parts"][0].get("type") == "text":
                    assistant_msg["content"] = round_data["content_parts"][0]["text"]
                else:
                    assistant_msg["content"] = round_data["content_parts"]
            else:
                assistant_msg["content"] = None

            if round_data["tool_calls"]:
                assistant_msg["tool_calls"] = round_data["tool_calls"]

            result.append(assistant_msg)
            result.extend(round_data["tool_results"])

        return result

    # ==================== 核心改动区域结束 ====================

    async def _convert_message_to_llm_dict(self, msg: Any, recency_rank: int) -> Optional[Dict[str, Any]]:
        """
        将非 Assistant 消息转换为 LLM 字典格式。
        Assistant 消息应使用 _convert_assistant_to_rounds 处理。
        """
        content_parts = []

        for sub in msg.sub_messages:
            if not self._should_include_sub_message(sub, recency_rank):
                continue

            if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                continue

            part = await self._convert_sub_message_to_part(sub)
            if part:
                content_parts.append(part)

        if not content_parts:
            return None

        res: Dict[str, Any] = {"role": msg.role}

        if msg.role == "tool" and hasattr(msg, "tool_call_id"):
            res["tool_call_id"] = msg.tool_call_id

        if len(content_parts) == 1 and content_parts[0]["type"] == "text":
            res["content"] = content_parts[0]["text"]
        else:
            res["content"] = content_parts

        return res

    def _should_include_sub_message(self, sub: Any, recency_rank: int) -> bool:
        """判断子消息是否符合包含条件。"""
        if self._type_filter and sub.type not in self._type_filter:
            return False

        if self._enable_cpl_filter:
            config = json.loads(sub.config) if isinstance(sub.config, str) else (sub.config or {})
            cpl = config.get("context_participation_length")
            if cpl == 0:
                return False
            if isinstance(cpl, int) and cpl > 0 and recency_rank > cpl:
                return False

        return True

    async def _convert_sub_message_to_part(self, sub: Any) -> Optional[Dict[str, Any]]:
        """将子消息转换为 LLM 内容分片。"""
        part = None
        if sub.type == schemas_enums.SubMessageType.FILE.value:
            part = await self._process_file_part(sub.content)
        elif sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
            part = None
        else:
            part = {"type": "text", "text": sub.content}

        if part and part.get("type") == "text" and self._content_limit:
            text = part["text"]
            if len(text) > self._content_limit:
                part["text"] = text[:self._content_limit] + "..."

        return part

    def _model_supports_images(self) -> bool:
        if not self._cached_model:
            return False

        meta = self._cached_model.meta_config

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

    async def _process_file_part(self, file_id: str) -> Optional[Dict[str, Any]]:
        if file_id in self._file_content_cache:
            return self._file_content_cache[file_id]

        file_service = FileService(self.db)
        db_file = await file_service.get_file(file_id)
        if not db_file:
            return None

        result = None
        if db_file.mime_type.startswith("image/") \
                and self._enable_image_with_model and self._model_supports_images():
            img_bytes = await file_service.get_file_content(file_id)
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            result = {"type": "image_url", "image_url": {"url": f"data:{db_file.mime_type};base64,{b64_data}"}}

        elif _is_text_mime_type(db_file.mime_type):
            text_bytes = await file_service.get_file_content(file_id)
            content = text_bytes.decode('utf-8')
            result = {"type": "text", "text": f"\n--- File: {db_file.filename} ---\n{content}\n--- End of File ---"}

        if result:
            self._file_content_cache[file_id] = result

        return result

    def _merge_consecutive_roles(self, payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not payload:
            return []
        merged = []
        for msg in payload:
            has_tool_calls = "tool_calls" in msg
            last_has_tool_calls = merged and "tool_calls" in merged[-1]
            is_tool_message = msg.get("role") == "tool"

            if (merged and merged[-1]["role"] == msg["role"]
                    and not has_tool_calls
                    and not last_has_tool_calls
                    and not is_tool_message
                    and isinstance(merged[-1].get("content"), str)
                    and isinstance(msg.get("content"), str)):

                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append(msg)
        return merged

    def _map_parameters(self, model_params_data: Any) -> Dict[str, Any]:
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

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers
