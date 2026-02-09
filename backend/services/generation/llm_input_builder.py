# backend/services/generation/llm_input_builder.py
import json
import base64
from typing import List, Dict, Any, Optional, Set, Tuple
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.crud import chat_crud, message_crud, setting_crud, file_crud, provider_crud, resource_crud
from backend.services.storage_service import storage_service
from backend.schemas import enums as schemas_enums, AIModel
from backend.schemas.message import McpToolContent
from backend.services.generation.llm_io import LLMInput
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS

# 以 application/* 开头但本质是文本的 MIME 类型
_KNOWN_TEXT_APPLICATION_TYPES = {
    "application/json", "application/xml", "application/sql",
    "application/javascript", "application/x-sh", "application/x-yaml",
    "application/rtf", "application/x-ipynb+json",
}

def _is_text_mime_type(mime_type: str) -> bool:
    """
    判断 MIME 类型是否可作为文本注入 LLM 上下文。
    - text/* 前缀通用放行
    - 已知的文本类 application/* 类型放行
    """
    if mime_type.startswith("text/"):
        return True
    return mime_type in _KNOWN_TEXT_APPLICATION_TYPES


class LLMInputBuilder:
    """
    LLM 输入构建器。
    负责从数据库或内存加载素材（Chat, Provider, Settings, Messages），
    并根据配置执行过滤、切片、多模态转换，最终生成标准化的 LLMInput 对象。
    支持内部缓存以优化在 ReAct 循环中的重复构建性能。
    """

    def __init__(self, db: AsyncSession, chat_id: str):
        """
        初始化构建器。
        :param db: 数据库会话
        :param chat_id: 当前操作的会话ID，用于确定上下文范围
        """
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

        # 新增配置项
        self._content_limit: Optional[int] = None
        self._flatten_history: bool = False
        self._append_prompt: Optional[str] = None
        self._tools: Optional[List[BaseTool]] = None

        # 内部数据缓存 (用于减少 I/O)
        self._cached_chat = None
        self._cached_settings = None
        self._cached_model = None
        self._file_content_cache: Dict[str, Dict[str, Any]] = {}

        # 运行时数据
        self.chat = None
        self.history = []
        self.settings = {}

    # --- 配置方法 (Fluent API) ---

    def slice_until_message(self, message_id: str, include_target: bool = False) -> "LLMInputBuilder":
        """
        设置上下文截断点。
        :param message_id: 截断点的消息ID
        :param include_target: 是否包含该消息本身。
                               False(默认): 截取到此消息之前 (用于 ReAct 上下文构建)
                               True: 包含此消息 (用于 ZipHistory 摘要构建)
        """
        self._cutoff_message_id = message_id
        self._cutoff_include = include_target
        return self

    def slice(self, start: int, end: Optional[int] = None) -> "LLMInputBuilder":
        """设置常规切片范围。"""
        self._slice_range = slice(start, end)
        return self

    def slice_head_tail(self, head: int, tail: int) -> "LLMInputBuilder":
        """设置头尾切片，常用于标题生成或长对话摘要。"""
        self._head_tail = (head, tail)
        return self

    def filter_sub_message_types(self, *types: str) -> "LLMInputBuilder":
        """设置允许的子消息类型过滤。"""
        self._type_filter = set(types)
        return self

    def enable_cpl_filter(self) -> "LLMInputBuilder":
        """启用上下文参与长度 (Context Participation Length) 过滤。"""
        self._enable_cpl_filter = True
        return self

    def enable_image_with_model(self) -> "LLMInputBuilder":
        """启用多模态图片处理。"""
        self._enable_image_with_model = True
        return self

    def disable_zip_history(self) -> "LLMInputBuilder":
        """禁用压缩历史逻辑，则直接忽略ZipHistory。"""
        self._enable_zip_history = False
        return self

    def use_global_model(self, setting_keys: List[str]) -> "LLMInputBuilder":
        """
        配置 Builder 使用全局设置中的模型，而非当前会话的模型。
        按顺序查找 setting_keys，使用第一个找到的有效模型 ID。
        """
        self._global_model_keys = setting_keys
        return self

    def set_system_prompt(self, prompt: str) -> "LLMInputBuilder":
        """
        强制设置 System Prompt，忽略 Chat 中的设置。
        """
        self._system_prompt_override = prompt
        return self

    def set_history_override(self, history: List[Any]) -> "LLMInputBuilder":
        """
        注入内存中的历史记录列表。
        设置此项后，Builder 将跳过从数据库加载消息的步骤，直接使用此列表。
        适用于 ReAct 循环中包含未持久化消息的场景。
        """
        self._history_override = history
        return self

    def enable_resource_prompt_merge(self) -> "LLMInputBuilder":
        """
        启用资源挂载功能。
        如果 Chat 配置了 resource_prompt_list，则提取资源内容并追加到 System Prompt。
        """
        self._enable_resource_merge = True
        return self

    def limit_sub_message_content(self, max_length: int) -> "LLMInputBuilder":
        """
        限制每个子消息文本内容的长度。
        超过长度将被截断并追加 '...'。
        """
        self._content_limit = max_length
        return self

    def flatten_history_to_single_user_message(self) -> "LLMInputBuilder":
        """
        将所有历史记录聚合成一条 User 消息。
        格式通常为:
        User: xxx
        Assistant: xxx
        ...
        """
        self._flatten_history = True
        return self

    def append_user_message(self, content: str) -> "LLMInputBuilder":
        """
        在历史记录末尾追加一条 User 消息（通常作为 Trigger Prompt）。
        Builder 会自动处理与上一条 User 消息的合并。
        """
        self._append_prompt = content
        return self

    def set_tools(self, tools: List[BaseTool]) -> "LLMInputBuilder":
        """
        设置 LangChain 工具列表。
        这些工具将直接传递给 Worker (Agent)。
        """
        self._tools = tools
        return self

    # --- 核心构建方法 ---

    async def build(self) -> LLMInput:
        """
        激活构建流程。
        执行数据加载、逻辑应用、结构转换，返回 LLMInput 实例。
        """
        await self._load_materials()

        # 1. 确定模型和 System Prompt
        model = await self._resolve_model()
        provider = model.provider

        system_prompt = self._system_prompt_override
        if system_prompt is None:
            system_prompt = self.chat.systemPrompt

        # 资源挂载逻辑：提取并追加资源内容
        if self._enable_resource_merge and self.chat.resource_prompt_list:
            resources = await resource_crud.get_resources_by_ids(self.db, self.chat.resource_prompt_list)
            resource_contents = [res.latest_version.content for res in resources if res.latest_version and res.latest_version.content]
            if resource_contents:
                merged_content = "\n\n".join(resource_contents)
                system_prompt = (system_prompt or "") + "\n\n" + merged_content

        # 2. 应用压缩历史逻辑
        effective_history = self.history
        if self._enable_zip_history:
            effective_history = await self._apply_zip_history_logic(effective_history)

        # 3. 应用切片逻辑
        effective_history = self._apply_slicing(effective_history)

        # 4. 核心转换：将消息对象集合转化为 Payload 结构
        messages_payload = await self._build_payload(effective_history)

        # 5. 注入 System Prompt
        if system_prompt:
            messages_payload.insert(0, {"role": "system", "content": system_prompt})

        # 6. 组装参数
        api_params = {}
        if not self._global_model_keys:
            api_params = self._map_parameters(self.chat.modelParameters)

        proxy_url = None
        if provider.use_proxy and self.settings.get("proxy_enabled") == "True":
            proxy_url = self.settings.get("proxy_url")

        return LLMInput(
            model_id=model.modelId,
            messages=messages_payload,
            parameters=api_params,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            tools=self._tools,
            tool_choice=None
        )

    # --- 内部处理逻辑 ---

    async def _load_materials(self):
        """加载构建所需的数据库素材，优先使用内部缓存。"""
        # 1. 加载 Chat (带缓存)
        if not self._cached_chat:
            self.chat = await chat_crud.get_chat(self.db, self.chat_id)
            if not self.chat:
                raise ValueError(f"Chat {self.chat_id} not found.")
            self._cached_chat = self.chat
        else:
            self.chat = self._cached_chat

        # 2. 加载历史消息
        if self._history_override is not None:
            self.history = self._history_override
        else:
            all_msgs = await message_crud.get_messages_by_chat(self.db, self.chat_id)

            if self._cutoff_message_id:
                try:
                    idx = next(i for i, m in enumerate(all_msgs) if m.id == self._cutoff_message_id)
                    # 如果包含目标，切片终点是 idx + 1；如果不包含，终点是 idx
                    end_index = idx + 1 if self._cutoff_include else idx
                    self.history = all_msgs[:end_index]
                except StopIteration:
                    # 如果找不到目标ID，通常意味着数据不一致，这里选择返回全部
                    self.history = all_msgs
            else:
                self.history = all_msgs

        # 3. 加载全局设置 (带缓存)
        if not self._cached_settings:
            all_settings = await setting_crud.get_all_settings(self.db)
            self.settings = {s.key: s.value for s in all_settings}
            self._cached_settings = self.settings
        else:
            self.settings = self._cached_settings

    async def _resolve_model(self) -> "AIModel":
        """决定最终使用哪个模型，支持缓存。"""
        if self._cached_model:
            return self._cached_model

        model = None
        # 1. 尝试从全局设置获取
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
            # 2. 默认：使用 Chat 绑定的模型
            if not self.chat.ai_model:
                raise ValueError("会话未配置模型")
            model = self.chat.ai_model

        self._cached_model = model
        return model

    def _apply_slicing(self, history: List[Any]) -> List[Any]:
        """应用配置的切片策略。"""
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

    async def _apply_zip_history_logic(self, history: List[Any]) -> List[Any]:
        """处理压缩历史逻辑：发现启用的 ZipHistory 则截断之前的内容并插入摘要。"""
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
        """将消息对象列表转换为 LLM 字典列表。"""
        payload = []
        total_count = len(history)

        for i, msg in enumerate(history):
            recency_rank = total_count - i

            # 1. 转换主消息
            llm_msg = await self._convert_message_to_llm_dict(msg, recency_rank)
            if llm_msg:
                payload.append(llm_msg)

            # 2. 如果是 Assistant 消息，检查并提取关联的工具执行结果（Role: Tool）
            if msg.role == schemas_enums.MessageRole.ASSISTANT.value:
                tool_results = self._extract_tool_results(msg)
                if tool_results:
                    payload.extend(tool_results)

        # 3. 处理历史聚合 (Flatten)
        if self._flatten_history and payload:
            flattened_content = ""
            for msg in payload:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                # 处理内容可能是字符串也可能是 list (多模态)
                content_str = ""
                raw_content = msg.get("content")

                if isinstance(raw_content, str):
                    content_str = raw_content
                elif isinstance(raw_content, list):
                    # 简化处理：如果是 flatten 模式，只取文本部分
                    texts = [item["text"] for item in raw_content if item.get("type") == "text"]
                    content_str = "\n".join(texts)

                if content_str:
                    flattened_content += f"{role_label}: {content_str}\n\n"

            # 重置 payload 为单条消息
            payload = [{"role": "user", "content": flattened_content.strip()}]

        # 4. 处理追加提示词 (Append Prompt)
        if self._append_prompt:
            payload.append({"role": "user", "content": self._append_prompt})

        # 5. 合并连续角色消息
        return self._merge_consecutive_roles(payload)

    def _extract_tool_results(self, msg: Any) -> List[Dict[str, Any]]:
        """从消息的子消息中提取工具执行结果，生成 role: tool 的消息列表。"""
        results = []
        for sub in msg.sub_messages:
            if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                try:
                    tool_content = McpToolContent.from_json_string(sub.content)
                    result_msg = tool_content.to_openai_tool_result_message()
                    if result_msg:
                        results.append(result_msg)
                except (ValueError, TypeError):
                    continue
        return results

    async def _convert_message_to_llm_dict(self, msg: Any, recency_rank: int) -> Optional[Dict[str, Any]]:
        """将单条消息转换为 LLM 字典格式，包含工具调用解析。"""
        content_parts = []
        tool_calls = []

        for sub in msg.sub_messages:
            # 1. 过滤逻辑
            if not self._should_include_sub_message(sub, recency_rank):
                continue

            # 2. 特殊类型处理：工具调用 (MCP_TOOL)
            if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                try:
                    # 使用 McpToolContent 解析并生成 OpenAI 格式的工具调用请求
                    tool_content = McpToolContent.from_json_string(sub.content)
                    tool_calls.append(tool_content.to_openai_tool_call())
                except (ValueError, TypeError):
                    continue
                continue

            # 3. 内容转换
            part = await self._convert_sub_message_to_part(sub)
            if part:
                content_parts.append(part)

        # 4. 构建返回对象
        if not content_parts and not tool_calls:
            return None

        res = {"role": msg.role}

        # 如果是 tool 类型的消息（通常由 ReAct 循环虚拟生成），必须携带 tool_call_id
        if msg.role == "tool" and hasattr(msg, "tool_call_id"):
            res["tool_call_id"] = msg.tool_call_id

        # 处理 Content
        if content_parts:
            # 如果只有一个文本部分，简化为字符串
            if len(content_parts) == 1 and content_parts[0]["type"] == "text":
                res["content"] = content_parts[0]["text"]
            else:
                res["content"] = content_parts
        else:
            # 有 tool_calls 但无 content，OpenAI 允许 content 为 null
            res["content"] = None

        # 处理 Tool Calls
        if tool_calls:
            res["tool_calls"] = tool_calls

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

        # 应用内容截断
        if part and part.get("type") == "text" and self._content_limit:
            text = part["text"]
            if len(text) > self._content_limit:
                part["text"] = text[:self._content_limit] + "..."

        return part

    def _model_supports_images(self) -> bool:
        """检查已解析的模型元配置中是否包含 image 模态。"""
        if not self._cached_model:
            return False

        meta = self._cached_model.meta_config

        # 1. 处理数据库可能返回的 JSON 字符串
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return False

        if not meta:
            return False
        # 2. 统一获取 input_modalities (兼容 Dict 和 Pydantic 对象)
        input_modalities = []
        if isinstance(meta, dict):
            input_modalities = meta.get('input_modalities')
        elif hasattr(meta, 'input_modalities'):
            input_modalities = meta.input_modalities

        return 'image' in (input_modalities or [])

    async def _process_file_part(self, file_id: str) -> Optional[Dict[str, Any]]:
        """处理文件内容的转换与读取，支持缓存以减少 I/O。"""
        if file_id in self._file_content_cache:
            return self._file_content_cache[file_id]

        db_file = await file_crud.get_file(self.db, file_id)
        if not db_file:
            return None

        result = None
        # 处理图片多模态
        if db_file.mime_type.startswith("image/") \
                and self._enable_image_with_model and self._model_supports_images():
            img_bytes = await storage_service.read_bytes(db_file.storage_path)
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            result = {"type": "image_url", "image_url": {"url": f"data:{db_file.mime_type};base64,{b64_data}"}}

        elif _is_text_mime_type(db_file.mime_type):
            text_bytes = await storage_service.read_bytes(db_file.storage_path)
            content = text_bytes.decode('utf-8')
            result = {"type": "text", "text": f"\n--- File: {db_file.filename} ---\n{content}\n--- End of File ---"}

        if result:
            self._file_content_cache[file_id] = result

        return result

    def _merge_consecutive_roles(self, payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并连续的同角色消息（可选，部分 API 要求角色交替）。"""
        if not payload:
            return []
        merged = []
        for msg in payload:
            # 注意：如果消息包含 tool_calls，通常不合并，因为 tool_calls 结构复杂
            has_tool_calls = "tool_calls" in msg
            last_has_tool_calls = merged and "tool_calls" in merged[-1]

            # 如果是 tool 类型的消息，绝对不能合并，因为每个 tool 消息都有唯一的 tool_call_id
            is_tool_message = msg.get("role") == "tool"

            if (merged and merged[-1]["role"] == msg["role"]
                    and not has_tool_calls
                    and not last_has_tool_calls
                    and not is_tool_message  # <--- 新增此条件
                    and isinstance(merged[-1].get("content"), str)
                    and isinstance(msg.get("content"), str)):

                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append(msg)
        return merged

    def _map_parameters(self, model_params_data: Any) -> Dict[str, Any]:
        """将数据库存储的扁平化参数映射为 LLM API 所需的层级结构。"""
        flat_params = {}
        if model_params_data:
            flat_params = json.loads(model_params_data) if isinstance(model_params_data, str) else model_params_data

        structured = {}
        param_def_map = {p.key: p for p in SUPPORTED_LLM_PARAMETERS}

        for key, value in flat_params.items():
            if key in ["max_context_messages", "stream", "enabled_mcp_ids"]:
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
