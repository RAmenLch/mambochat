# backend/services/generation/context_builder.py

import json
import base64
from datetime import datetime as dt
from typing import List, Dict, Any, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, ErrorContent
from backend.services.file_service import FileService
from backend.services.generation.core.llm_io import MessageContext, MessageSchema, SubMessageSchema

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
        self._file_content_cache: Dict[str, Dict[str, Any]] = {}

    async def build(self, raw_history: List[MessageSchema], system_prompt: Optional[str] = None) -> MessageContext:
        """
        核心装配方法。
        传入原始历史消息列表，输出标准化的 MessageContext。
        """
        effective_history = raw_history

        # 1. 应用历史压缩逻辑 (内存级)
        if self.enable_zip_history:
            effective_history = self._apply_zip_history_logic(effective_history)

        # 2. 应用切片逻辑 (内存级)
        effective_history = self._apply_slicing(effective_history)

        # 3. 应用最大上下文限制 (内存级)
        if self.max_context_messages:
            effective_history = self._apply_max_context_limit(effective_history)

        # 4. 构建 Payload 并执行 I/O 操作 (仅对最终保留的消息执行)
        messages_payload = await self._build_payload(effective_history)

        # 5. 注入 System Prompt
        if system_prompt:
            messages_payload.insert(0, {"role": "system", "content": system_prompt})

        return MessageContext(messages=messages_payload)

    # --- 内存级过滤与切片逻辑 ---

    def _apply_zip_history_logic(self, history: List[MessageSchema]) -> List[MessageSchema]:
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
            return [user_msg, assistant_msg] + history[last_enabled_zip_index + 1:]

        return history

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

        if self.flatten_history and payload:
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

        if self.append_prompt:
            payload.append({"role": "user", "content": self.append_prompt})

        return self._merge_consecutive_roles(payload)

    async def _convert_assistant_to_rounds(self, msg: MessageSchema, recency_rank: int) -> List[Dict[str, Any]]:
        # 按 createdAt 排序，保证时间顺序
        sorted_subs = sorted(
            msg.sub_messages,
            key=lambda s: (s.createdAt or dt.min, s.sortOrder)
        )

        rounds: List[Dict[str, List]] = []
        current_round: Dict[str, List] = {"content_parts": [], "tool_calls": [], "tool_results": []}
        seen_tool_in_round = False

        for sub in sorted_subs:
            is_mcp_tool = (sub.type == schemas_enums.SubMessageType.MCP_TOOL.value)

            if is_mcp_tool:
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
                if seen_tool_in_round:
                    if current_round["content_parts"] or current_round["tool_calls"]:
                        rounds.append(current_round)
                    current_round = {"content_parts": [], "tool_calls": [], "tool_results": []}
                    seen_tool_in_round = False

                if self._should_include_sub_message(sub, recency_rank):
                    part = await self._convert_sub_message_to_part(sub)
                    if part:
                        current_round["content_parts"].append(part)

        if current_round["content_parts"] or current_round["tool_calls"]:
            rounds.append(current_round)

        result = []
        for round_data in rounds:
            assistant_msg: Dict[str, Any] = {"role": "assistant"}

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

    async def _convert_sub_message_to_part(self, sub: SubMessageSchema) -> Optional[Dict[str, Any]]:
        part = None
        if sub.type == schemas_enums.SubMessageType.FILE.value:
            part = await self._process_file_part(sub.content)
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

        if part and part.get("type") == "text" and self.content_limit:
            text = part["text"]
            if len(text) > self.content_limit:
                part["text"] = text[:self.content_limit] + "..."

        return part

    async def _process_file_part(self, file_id: str) -> Optional[Dict[str, Any]]:
        if file_id in self._file_content_cache:
            return self._file_content_cache[file_id]

        file_service = FileService(self.db)
        db_file = await file_service.get_file(file_id)
        if not db_file:
            return None

        result = None
        mime = db_file.mime_type

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
