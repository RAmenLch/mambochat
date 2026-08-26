# backend/services/generation/context_builder.py

import json
import base64
from datetime import datetime as dt
from typing import List, Dict, Any, Optional, Set, Tuple, Union

from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import HumanMessage

from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, ErrorContent
from backend.services.file_service import FileService
from backend.services.generation.core.llm_io import MessageContext, MessageSchema, SubMessageSchema
from backend.services.generation.agent.user_file_copy_service import derive_file_extension

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


# 文件大小限制常量 (字节)
_MAX_AUDIO_SIZE = 25 * 1024 * 1024   # 25MB
_MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50MB
_MAX_FILE_SIZE = 20 * 1024 * 1024    # 20MB (PDF等)


class MessageContextBuilder:
    """
    消息上下文装配器。
    负责执行消息的切片、过滤、多模态转换（包含 I/O 操作），以及多轮工具调用的拆分。
    保证 I/O 操作严格在内存过滤和切片之后执行，避免额外开销。
    """

    def __init__(
            self,
            db: AsyncSession,
            type_filter: Optional[Set[str]] = None,
            enable_cpl_filter: bool = False,
            enable_image_with_model: bool = False,
            model_supports_images: bool = False,
            model_supports_audio: bool = False,
            model_supports_video: bool = False,
            model_supports_file: bool = False,
            enable_zip_history: bool = True,
            content_limit: Optional[int] = None,
            flatten_history: bool = False,
            append_prompt: Optional[str] = None,
            max_context_messages: Optional[int] = None,
            slice_range: Optional[slice] = None,
            head_tail: Optional[Tuple[int, int]] = None,
            language: Optional[str] = None
    ):
        self.db = db

        # 过滤与切片规则
        self.type_filter = type_filter
        self.enable_cpl_filter = enable_cpl_filter
        self.enable_image_with_model = enable_image_with_model
        self.model_supports_images = model_supports_images
        self.model_supports_audio = model_supports_audio
        self.model_supports_video = model_supports_video
        self.model_supports_file = model_supports_file
        self.enable_zip_history = enable_zip_history
        self.content_limit = content_limit
        self.flatten_history = flatten_history
        self.append_prompt = append_prompt
        self.max_context_messages = max_context_messages
        self.slice_range = slice_range
        self.head_tail = head_tail
        self.language = language

        # 内部缓存，防止同一文件在单次装配中重复读取
        self._file_content_cache: Dict[Any, Any] = {}

        # 自动摘要重算：由 _apply_zip_history_logic 填充，_build_payload 消费
        self._auto_target_sub_msg_id: Optional[str] = None
        self._auto_summary_content: Optional[str] = None
        self._auto_cutoff_index: Optional[int] = None

    async def build(self, raw_history: List[MessageSchema], system_prompt: Optional[str] = None) -> MessageContext:
        """
        核心装配方法。
        传入原始历史消息列表，输出标准化的 MessageContext。
        """
        effective_history = raw_history

        # 1. 应用历史压缩逻辑 (内存级)
        #    自动摘要 → 跳过替换，仅提取元数据供后续 cutoff 重算
        #    手动摘要 → 保持原有替换逻辑
        if self.enable_zip_history:
            effective_history = self._apply_zip_history_logic(effective_history)

        # 2. 应用切片逻辑 (内存级)
        effective_history = self._apply_slicing(effective_history)

        # 3. 应用最大上下文限制 (内存级)
        if self.max_context_messages:
            effective_history = self._apply_max_context_limit(effective_history)

        # 4. 构建 Payload（内部完成 auto target 搜索 + merge 追踪 + cutoff 计算）
        messages_payload = await self._build_payload(effective_history)

        # 5. 注入 System Prompt（插入到 index=0，后续消息整体后移 1 位）
        if system_prompt:
            messages_payload.insert(0, {"role": "system", "content": system_prompt})
            # cutoff_index 基于注入前的位置计算，需要 +1 补偿 system_prompt 的偏移
            if self._auto_cutoff_index is not None:
                self._auto_cutoff_index += 1

        # 6. 构造自动摘要事件（供 Worker 同步 LangGraph state）
        auto_event = self._build_auto_summarization_event()

        return MessageContext(
            messages=messages_payload,
            auto_summarization_event=auto_event,
        )

    # --- 内存级过滤与切片逻辑 ---

    def _apply_zip_history_logic(self, history: List[MessageSchema]) -> List[MessageSchema]:
        last_enabled_zip_index = -1
        zip_content: Optional[str] = None
        target_sub_msg_id: Optional[str] = None
        is_auto: bool = False

        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            for sub in msg.sub_messages:
                if sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
                    config = json.loads(sub.config) if isinstance(sub.config, str) else (sub.config or {})
                    if config.get('zip_enable') is True:
                        last_enabled_zip_index = i
                        zip_content = sub.content
                        target_sub_msg_id = config.get('target_sub_msg_id')
                        is_auto = config.get('auto_summary') is True
                        break
            if last_enabled_zip_index != -1:
                break

        if last_enabled_zip_index == -1 or not zip_content:
            self._auto_target_sub_msg_id = None
            self._auto_summary_content = None
            return history

        if is_auto:
            # 自动摘要：不替换历史（由 middleware 的 _summarization_event 处理）
            # 仅记录元数据供后续 cutoff_index 重算
            self._auto_target_sub_msg_id = target_sub_msg_id
            self._auto_summary_content = zip_content
            return history

        # ── 手动摘要：保持原有替换逻辑 ──
        self._auto_target_sub_msg_id = None
        self._auto_summary_content = None

        zip_summary_prompt = "对之前的对话进行了总结摘要。" if self.language == "zh-CN" else "A summary of the previous conversation has been generated."
        user_msg = MessageSchema(
            role=schemas_enums.MessageRole.USER.value,
            sub_messages=[SubMessageSchema(content=zip_summary_prompt,
                                          type=schemas_enums.SubMessageType.NORMAL.value, config='{}')]
        )
        assistant_msg = MessageSchema(
            role=schemas_enums.MessageRole.ASSISTANT.value,
            sub_messages=[
                SubMessageSchema(content=zip_content, type=schemas_enums.SubMessageType.NORMAL.value, config='{}')]
        )

        if target_sub_msg_id:
            # ── SubMessage 粒度：保留 zip 所在父消息中 target_sub_msg_id 之后的子消息 ──
            zip_parent_msg = history[last_enabled_zip_index]
            sorted_subs = sorted(
                zip_parent_msg.sub_messages,
                key=lambda s: (s.createdAt or dt.min, s.sortOrder),
            )
            target_found = False
            kept_subs: List[SubMessageSchema] = []
            for sub in sorted_subs:
                if sub.id == target_sub_msg_id:
                    target_found = True
                    continue  # target_sub_msg_id 本身已被摘要覆盖，不保留
                if target_found:
                    kept_subs.append(sub)
            if kept_subs:
                trimmed_msg = MessageSchema(
                    role=zip_parent_msg.role,
                    id=zip_parent_msg.id,
                    sub_messages=kept_subs,
                )
                return [user_msg, assistant_msg, trimmed_msg] + history[last_enabled_zip_index + 1:]
            else:
                # 没有剩余的 sub_message 则视为与 message 粒度一致
                return [user_msg, assistant_msg] + history[last_enabled_zip_index + 1:]
        else:
            # ── Message 粒度：zip 覆盖 target_message_id（包含）之前的所有消息 ──
            return [user_msg, assistant_msg] + history[last_enabled_zip_index + 1:]

    def _apply_slicing(self, history: List[MessageSchema]) -> List[MessageSchema]:
        if not history:
            return []

        if self.head_tail:
            head, tail = self.head_tail
            if len(history) <= (head + tail):
                return history
            return history[:head] + history[-tail:]

        if self.slice_range:
            return history[self.slice_range]

        return history

    def _apply_max_context_limit(self, history: List[MessageSchema]) -> List[MessageSchema]:
        if not history or not self.max_context_messages:
            return history

        limit = self.max_context_messages
        # 保证成对截断 (User + Assistant)
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

    # --- 消息转换与 I/O 逻辑 ---

    async def _build_payload(self, history: List[MessageSchema]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
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

        # ── 阶段 A：搜索 auto target（在 merge/flatten 之前）──
        target_position: Optional[int] = None
        if self._auto_target_sub_msg_id:
            for idx, m in enumerate(payload):
                # 仅匹配 ToolMessage：AIMessage 可能与 ToolMessage 共享 id
                # （当 MCP_TOOL 是该轮最后一个子消息时，last_sub_id == sub.id）
                if m.get("id") == self._auto_target_sub_msg_id and m.get("role") == "tool":
                    target_position = idx
                    break
            if target_position is None:
                # target 消息已被删除 → 摘要失效
                self._auto_target_sub_msg_id = None
                self._auto_summary_content = None

        if self.flatten_history and payload:
            # flatten 会破坏所有 id 跟踪 → 自动摘要失效
            self._auto_target_sub_msg_id = None
            self._auto_summary_content = None
            target_position = None

            flattened_content = ""
            last_id = payload[-1].get("id") if payload else None
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

            flattened_msg: Dict[str, Any] = {"role": "user", "content": flattened_content.strip()}
            if last_id:
                flattened_msg["id"] = last_id
            payload = [flattened_msg]

        if self.append_prompt:
            payload.append({"role": "user", "content": self.append_prompt})

        # ── 阶段 B：merge（追踪版，仅当有 target 时）──
        if target_position is not None:
            payload = self._merge_consecutive_roles_with_tracking(payload, target_position)
        else:
            payload = self._merge_consecutive_roles(payload)
            self._auto_cutoff_index = None

        return payload

    @staticmethod
    def _extract_run_uuid(sub: SubMessageSchema) -> Optional[str]:
        """解析子消息所属的模型调用轮次（run_uuid）。

        - MCP_TOOL：从 content 的 run_uuid 字段取（落库时由 create_call_instruction 写入）；
        - NORMAL / REASONING：从 id 派生（<run_uuid>-N / <run_uuid>-R）。

        旧数据（未记录 run_uuid）返回 None，由调用方走原有间隔切分逻辑兜底。
        """
        if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
            try:
                content_obj = McpToolContent.from_json_string(sub.content)
                return content_obj.run_uuid
            except (ValueError, TypeError):
                return None
        sid = sub.id or ""
        if len(sid) > 2 and (sid.endswith("-N") or sid.endswith("-R")):
            return sid[:-2]
        return None

    async def _build_tool_media_content(
        self, media_list: Optional[List[Any]]
    ) -> List[Dict[str, Any]]:
        """将多模态工具的媒体引用还原为与 ckpt 一致的 content 块结构。

        块结构必须与 ``mambo_agents`` backend_tools 构造的 ``content_blocks`` 一致：
        ``{"type": <image/audio/video/file>, "base64": ..., "mime_type": ...}``，
        否则重建的 tool result 与 ckpt 中的 ToolMessage 不一致，会破坏上下文缓存。
        注意：不能复用 ``_process_file_part_legacy`` 的 ``image_url`` API 格式。
        """
        file_service = FileService(self.db)
        blocks: List[Dict[str, Any]] = []
        for m in media_list or []:
            if m is None:
                continue
            file_id = getattr(m, "file_id", None)
            if not file_id:
                continue
            try:
                raw = await file_service.get_file_content(file_id)
            except Exception:
                continue
            blocks.append({
                "type": getattr(m, "file_type", "file"),
                "base64": base64.b64encode(raw).decode("utf-8"),
                "mime_type": getattr(m, "mime_type", "application/octet-stream"),
            })
        return blocks

    async def _convert_assistant_to_rounds(self, msg: MessageSchema, recency_rank: int) -> List[Dict[str, Any]]:
        # 按 createdAt 排序，保证时间顺序
        sorted_subs = sorted(
            msg.sub_messages,
            key=lambda s: (s.createdAt or dt.min, s.sortOrder)
        )

        rounds: List[Dict[str, List]] = []
        current_round: Dict[str, List] = {"content_parts": [], "tool_calls": [], "tool_results": [], "last_sub_id": None, "run_uuid": None}
        seen_tool_in_round = False

        for sub in sorted_subs:
            is_mcp_tool = (sub.type == schemas_enums.SubMessageType.MCP_TOOL.value)

            if is_mcp_tool:
                sub_run_uuid = self._extract_run_uuid(sub)
                # run_uuid 变化（顺序调用而非并行）→ 先闭合当前 round，精准还原独立 AI 轮次。
                # 仅当新 MCP_TOOL 与当前 round 归属不同轮次时切分；run_uuid 缺失（旧数据）走原有逻辑。
                if (
                    seen_tool_in_round
                    and sub_run_uuid
                    and current_round.get("run_uuid")
                    and sub_run_uuid != current_round["run_uuid"]
                ):
                    if current_round["content_parts"] or current_round["tool_calls"]:
                        rounds.append(current_round)
                    current_round = {"content_parts": [], "tool_calls": [], "tool_results": [], "last_sub_id": None, "run_uuid": None}
                    seen_tool_in_round = False

                seen_tool_in_round = True
                if self._should_include_sub_message(sub, recency_rank):
                    try:
                        tool_content = McpToolContent.from_json_string(sub.content)
                        current_round["tool_calls"].append(tool_content.to_openai_tool_call())
                        result_msg = tool_content.to_openai_tool_result_message()
                        if result_msg:
                            result_msg["id"] = sub.id
                            if tool_content.is_multimodal:
                                result_msg["content"] = await self._build_tool_media_content(tool_content.media)
                            current_round["tool_results"].append(result_msg)
                        current_round["last_sub_id"] = sub.id
                        if not current_round["run_uuid"] and sub_run_uuid:
                            current_round["run_uuid"] = sub_run_uuid
                    except (ValueError, TypeError):
                        continue
            else:
                if seen_tool_in_round:
                    if current_round["content_parts"] or current_round["tool_calls"]:
                        rounds.append(current_round)
                    current_round = {"content_parts": [], "tool_calls": [], "tool_results": [], "last_sub_id": None, "run_uuid": None}
                    seen_tool_in_round = False

                if self._should_include_sub_message(sub, recency_rank):
                    part = await self._convert_sub_message_to_part(sub, schemas_enums.MessageRole.ASSISTANT.value)
                    if part:
                        current_round["content_parts"].append(part)
                        current_round["last_sub_id"] = sub.id

        if current_round["content_parts"] or current_round["tool_calls"]:
            rounds.append(current_round)

        result = []
        for round_data in rounds:
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            last_id = round_data.get("last_sub_id")
            if last_id:
                assistant_msg["id"] = last_id

            # 从 content_parts 中分离 reasoning_text（REASONING 类型子消息）
            # 与普通 content 分开，映射到独立的 API 字段
            reasoning_texts = []
            content_only_parts = []
            for p in round_data["content_parts"]:
                if p.get("type") == "reasoning_text":
                    reasoning_texts.append(p.get("text", ""))
                else:
                    content_only_parts.append(p)

            if content_only_parts:
                if len(content_only_parts) == 1 and content_only_parts[0].get("type") == "text":
                    assistant_msg["content"] = content_only_parts[0]["text"]
                else:
                    assistant_msg["content"] = content_only_parts
            else:
                assistant_msg["content"] = None

            if round_data["tool_calls"]:
                assistant_msg["tool_calls"] = round_data["tool_calls"]

            # 将 REASONING 内容放入独立字段（仅在有内容时添加，不影响其他模型）
            if reasoning_texts:
                assistant_msg["reasoning_content"] = "".join(reasoning_texts)

            result.append(assistant_msg)
            result.extend(round_data["tool_results"])

        return result

    async def _convert_message_to_llm_dict(self, msg: MessageSchema, recency_rank: int) -> Optional[Dict[str, Any]]:
        content_parts = []
        last_sub_id: Optional[str] = None

        for sub in msg.sub_messages:
            if not self._should_include_sub_message(sub, recency_rank):
                continue

            if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                continue

            part = await self._convert_sub_message_to_part(sub, msg.role)
            if part:
                if isinstance(part, list):
                    content_parts.extend(part)
                else:
                    content_parts.append(part)
                last_sub_id = sub.id

        if not content_parts:
            return None

        res: Dict[str, Any] = {"role": msg.role}
        if last_sub_id:
            res["id"] = last_sub_id

        if msg.role == "tool":
            tool_call_id = getattr(msg, 'tool_call_id', None)
            if tool_call_id:
                res["tool_call_id"] = tool_call_id

        if len(content_parts) == 1 and content_parts[0]["type"] == "text":
            res["content"] = content_parts[0]["text"]
        else:
            res["content"] = content_parts

        return res

    def _should_include_sub_message(self, sub: SubMessageSchema, recency_rank: int) -> bool:
        if self.type_filter and sub.type not in self.type_filter:
            return False

        if self.enable_cpl_filter:
            config = json.loads(sub.config) if isinstance(sub.config, str) else (sub.config or {})
            cpl = config.get("context_participation_length")
            if cpl == 0:
                return False
            if isinstance(cpl, int) and cpl > 0 and recency_rank > cpl:
                return False

        return True

    async def _convert_sub_message_to_part(
        self, sub: SubMessageSchema, role: str
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        part = None
        if sub.type == schemas_enums.SubMessageType.FILE.value:
            part = await self._process_file_part(sub.content, sub, role)
        elif sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
            part = None
        elif sub.type == schemas_enums.SubMessageType.ERROR.value:
            try:
                error_obj = ErrorContent.from_json_string(sub.content)
                part = {"type": "text", "text": error_obj.message}
            except (ValueError, TypeError):
                part = {"type": "text", "text": sub.content}
        elif sub.type == schemas_enums.SubMessageType.REASONING.value:
            # REASONING 内容需要映射到独立的 reasoning_content 字段，不混入 content
            part = {"type": "reasoning_text", "text": sub.content}
        else:
            part = {"type": "text", "text": sub.content}

        if isinstance(part, dict) and part.get("type") == "text" and self.content_limit:
            text = part["text"]
            if len(text) > self.content_limit:
                part["text"] = text[:self.content_limit] + "..."

        return part

    @staticmethod
    def _copy_status_of(sub: SubMessageSchema) -> Optional[str]:
        """读取子消息上固化的副本写入标志位（file_copy_status）。"""
        raw = getattr(sub, "config", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                return None
        if isinstance(raw, dict):
            return raw.get("file_copy_status")
        return None

    async def _process_file_part(
        self, file_id: str, sub: SubMessageSchema, role: str
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """转换 FILE 子消息为 LLM content part。

        - USER 角色：始终附加文件信息文本（需求 1），副本写入成功（file_copy_status=ok）时
          附带路径映射（需求 3.2）；渲染只依赖持久化数据，保证同版本内逐字节稳定。
        - 其他角色（assistant 的 show 工具文件等）：保持原有行为逐字节不变。
        """
        copy_status = self._copy_status_of(sub)
        cache_key = (file_id, role, copy_status)
        if cache_key in self._file_content_cache:
            return self._file_content_cache[cache_key]

        file_service = FileService(self.db)
        db_file = await file_service.get_file(file_id)
        if not db_file:
            return None

        if role == schemas_enums.MessageRole.USER.value:
            result = await self._process_user_file_part(file_service, db_file, file_id, sub)
        else:
            result = await self._process_file_part_legacy(file_service, db_file)

        if result:
            self._file_content_cache[cache_key] = result

        return result

    async def _process_file_part_legacy(
        self, file_service: FileService, db_file: Any
    ) -> Optional[Dict[str, Any]]:
        """非 USER 角色（assistant show 工具文件等）的原有转换逻辑，逐字节保持。"""
        mime = db_file.mime_type
        file_id = db_file.id
        result = None

        # --- 图片 (保持现有 OpenAI 格式) ---
        if mime.startswith("image/") \
                and self.enable_image_with_model and self.model_supports_images:
            img_bytes = await file_service.get_file_content(file_id)
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            result = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_data}"}}

        # --- 音频 (LangChain 标准格式) ---
        elif mime.startswith("audio/") and self.model_supports_audio:
            audio_bytes = await file_service.get_file_content(file_id)
            if len(audio_bytes) <= _MAX_AUDIO_SIZE:
                b64_data = base64.b64encode(audio_bytes).decode('utf-8')
                result = {"type": "audio", "base64": b64_data, "mime_type": mime}
            else:
                size_mb = len(audio_bytes) // (1024 * 1024)
                result = {"type": "text", "text": f"\n[用户上传了音频文件: {db_file.filename} ({size_mb}MB), 文件过大无法发送给模型]"}

        # --- 视频 (LangChain 标准格式) ---
        elif mime.startswith("video/") and self.model_supports_video:
            video_bytes = await file_service.get_file_content(file_id)
            if len(video_bytes) <= _MAX_VIDEO_SIZE:
                b64_data = base64.b64encode(video_bytes).decode('utf-8')
                result = {"type": "video", "base64": b64_data, "mime_type": mime}
            else:
                size_mb = len(video_bytes) // (1024 * 1024)
                result = {"type": "text", "text": f"\n[用户上传了视频文件: {db_file.filename} ({size_mb}MB), 文件过大无法发送给模型]"}

        # --- PDF 等文件 (LangChain 标准格式) ---
        elif mime == "application/pdf" and self.model_supports_file:
            pdf_bytes = await file_service.get_file_content(file_id)
            if len(pdf_bytes) <= _MAX_FILE_SIZE:
                b64_data = base64.b64encode(pdf_bytes).decode('utf-8')
                result = {"type": "file", "base64": b64_data, "mime_type": mime}
            else:
                size_mb = len(pdf_bytes) // (1024 * 1024)
                result = {"type": "text", "text": f"\n[用户上传了PDF文件: {db_file.filename} ({size_mb}MB), 文件过大无法发送给模型]"}

        # --- 文本文件 (保持现有逻辑) ---
        elif _is_text_mime_type(mime):
            text_bytes = await file_service.get_file_content(file_id)
            content = text_bytes.decode('utf-8')
            result = {"type": "text", "text": f"\n--- File: {db_file.filename} ---\n{content}\n--- End of File ---"}

        # --- 不支持的模态 → 文本占位符 ---
        else:
            category = ("图片" if mime.startswith("image/") else
                        "音频" if mime.startswith("audio/") else
                        "视频" if mime.startswith("video/") else
                        "PDF文档" if mime == "application/pdf" else "文件")
            support_hint = ""
            if mime.startswith("image/") and not self.model_supports_images:
                support_hint = "，当前模型不支持图片输入"
            elif mime.startswith("audio/") and not self.model_supports_audio:
                support_hint = "，当前模型不支持音频输入"
            elif mime.startswith("video/") and not self.model_supports_video:
                support_hint = "，当前模型不支持视频输入"
            elif mime == "application/pdf" and not self.model_supports_file:
                support_hint = "，当前模型不支持PDF输入"
            result = {"type": "text", "text": f"\n[用户上传了{category}: {db_file.filename}{support_hint}]"}

        return result

    async def _process_user_file_part(
        self, file_service: FileService, db_file: Any, file_id: str, sub: SubMessageSchema
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """用户消息的文件转换：始终附带文件信息，副本写入成功时附带路径映射。"""
        mime = db_file.mime_type
        category = ("图片" if mime.startswith("image/") else
                    "音频" if mime.startswith("audio/") else
                    "视频" if mime.startswith("video/") else
                    "PDF文档" if mime == "application/pdf" else "文件")

        info_body = f"[用户上传了{category}: {db_file.filename}"
        if self._copy_status_of(sub) == "ok":
            ext = derive_file_extension(db_file.filename, mime)
            target = f"/.mambo/chat_user_file/{file_id}"
            if ext:
                target += f".{ext}"
            info_body += f" | 副本文件 -> {target}"
        info_body += "]"

        # --- 图片 (OpenAI 格式) ---
        if mime.startswith("image/") \
                and self.enable_image_with_model and self.model_supports_images:
            img_bytes = await file_service.get_file_content(file_id)
            b64_data = base64.b64encode(img_bytes).decode('utf-8')
            return [
                {"type": "text", "text": f"\n{info_body}"},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_data}"}},
            ]

        # --- 音频 (LangChain 标准格式) ---
        if mime.startswith("audio/") and self.model_supports_audio:
            audio_bytes = await file_service.get_file_content(file_id)
            if len(audio_bytes) <= _MAX_AUDIO_SIZE:
                b64_data = base64.b64encode(audio_bytes).decode('utf-8')
                return [
                    {"type": "text", "text": f"\n{info_body}"},
                    {"type": "audio", "base64": b64_data, "mime_type": mime},
                ]
            return {"type": "text", "text": f"\n{info_body}，文件过大无法发送给模型"}

        # --- 视频 (LangChain 标准格式) ---
        if mime.startswith("video/") and self.model_supports_video:
            video_bytes = await file_service.get_file_content(file_id)
            if len(video_bytes) <= _MAX_VIDEO_SIZE:
                b64_data = base64.b64encode(video_bytes).decode('utf-8')
                return [
                    {"type": "text", "text": f"\n{info_body}"},
                    {"type": "video", "base64": b64_data, "mime_type": mime},
                ]
            return {"type": "text", "text": f"\n{info_body}，文件过大无法发送给模型"}

        # --- PDF 等文件 (LangChain 标准格式) ---
        if mime == "application/pdf" and self.model_supports_file:
            pdf_bytes = await file_service.get_file_content(file_id)
            if len(pdf_bytes) <= _MAX_FILE_SIZE:
                b64_data = base64.b64encode(pdf_bytes).decode('utf-8')
                return [
                    {"type": "text", "text": f"\n{info_body}"},
                    {"type": "file", "base64": b64_data, "mime_type": mime},
                ]
            return {"type": "text", "text": f"\n{info_body}，文件过大无法发送给模型"}

        # --- 文本文件 ---
        if _is_text_mime_type(mime):
            text_bytes = await file_service.get_file_content(file_id)
            content = text_bytes.decode('utf-8')
            return {"type": "text", "text": f"\n{info_body}\n--- File: {db_file.filename} ---\n{content}\n--- End of File ---"}

        # --- 不支持的模态 → 附带"模型不支持"提示 ---
        support_hint = ""
        if mime.startswith("image/") and not self.model_supports_images:
            support_hint = "，当前模型不支持图片输入"
        elif mime.startswith("audio/") and not self.model_supports_audio:
            support_hint = "，当前模型不支持音频输入"
        elif mime.startswith("video/") and not self.model_supports_video:
            support_hint = "，当前模型不支持视频输入"
        elif mime == "application/pdf" and not self.model_supports_file:
            support_hint = "，当前模型不支持PDF输入"
        return {"type": "text", "text": f"\n{info_body}{support_hint}"}

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
                if "id" in msg:
                    merged[-1]["id"] = msg["id"]
            else:
                merged.append(msg)
        return merged

    def _merge_consecutive_roles_with_tracking(
        self,
        payload: List[Dict[str, Any]],
        target_position: int,
    ) -> List[Dict[str, Any]]:
        """合并相邻同角色消息，同时追踪 target 被合并后的新位置。

        追踪策略：在处理到 i == target_position 的那一刻，
        target 一定在 merged[-1]（要么刚刚 append，要么刚被 merge 进前一条）。
        此时记录 len(merged) - 1 即为 target 在最终列表中的位置。
        """
        if not payload:
            self._auto_cutoff_index = None
            return []

        merged: List[Dict[str, Any]] = []
        target_new_pos: Optional[int] = None

        for i, msg in enumerate(payload):
            has_tool_calls = "tool_calls" in msg
            last_has_tool_calls = merged and "tool_calls" in merged[-1]
            is_tool_message = msg.get("role") == "tool"

            can_merge = (
                merged
                and merged[-1]["role"] == msg["role"]
                and not has_tool_calls
                and not last_has_tool_calls
                and not is_tool_message
                and isinstance(merged[-1].get("content"), str)
                and isinstance(msg.get("content"), str)
            )

            if can_merge:
                merged[-1]["content"] += "\n" + msg["content"]
                if "id" in msg:
                    merged[-1]["id"] = msg["id"]
            else:
                merged.append(msg)

            if i == target_position:
                target_new_pos = len(merged) - 1

        if target_new_pos is not None:
            self._auto_cutoff_index = target_new_pos + 1
        else:
            self._auto_cutoff_index = None

        return merged

    def _build_auto_summarization_event(self) -> Optional[Dict[str, Any]]:
        """由 build() 在最后调用，构造投递给 Worker 的 SummarizationEvent。

        基于 DB 中 auto ZipHistory 的内容和重算的 cutoff_index 构建，
        如果无有效自动摘要则返回 None。
        """
        if self._auto_cutoff_index is None or not self._auto_summary_content:
            return None

        return {
            "cutoff_index": self._auto_cutoff_index,
            "summary_message": HumanMessage(
                content=self._auto_summary_content,
                additional_kwargs={"lc_source": "summarization"},
            ),
            "file_path": None,
            # 重建事件仅用于同步 LangGraph state,下游 middleware 只消费
            # cutoff_index 和 summary_message;last_summarized_message 是
            # 实时压缩时用于落库 ZipHistory 定位的,此处无从恢复,补 None 满足
            # SummarizationEvent(TypedDict) 的必填校验。
            "last_summarized_message": None,
        }
