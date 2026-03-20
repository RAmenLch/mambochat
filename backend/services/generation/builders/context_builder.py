# backend/services/generation/context_builder.py

import json
import base64
from datetime import datetime as dt
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent
from backend.services.file_service import FileService
from backend.services.generation.core.llm_io import MessageContext

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
            enable_zip_history: bool = True,
            content_limit: Optional[int] = None,
            flatten_history: bool = False,
            append_prompt: Optional[str] = None,
            max_context_messages: Optional[int] = None,
            slice_range: Optional[slice] = None,
            head_tail: Optional[Tuple[int, int]] = None
    ):
        self.db = db

        # 过滤与切片规则
        self.type_filter = type_filter
        self.enable_cpl_filter = enable_cpl_filter
        self.enable_image_with_model = enable_image_with_model
        self.model_supports_images = model_supports_images
        self.enable_zip_history = enable_zip_history
        self.content_limit = content_limit
        self.flatten_history = flatten_history
        self.append_prompt = append_prompt
        self.max_context_messages = max_context_messages
        self.slice_range = slice_range
        self.head_tail = head_tail

        # 内部缓存，防止同一文件在单次装配中重复读取
        self._file_content_cache: Dict[str, Dict[str, Any]] = {}

    async def build(self, raw_history: List[Any], system_prompt: Optional[str] = None) -> MessageContext:
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

    def _apply_zip_history_logic(self, history: List[Any]) -> List[Any]:
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

    def _apply_slicing(self, history: List[Any]) -> List[Any]:
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

    def _apply_max_context_limit(self, history: List[Any]) -> List[Any]:
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

    async def _build_payload(self, history: List[Any]) -> List[Dict[str, Any]]:
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

    async def _convert_assistant_to_rounds(self, msg: Any, recency_rank: int) -> List[Dict[str, Any]]:
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

    async def _convert_message_to_llm_dict(self, msg: Any, recency_rank: int) -> Optional[Dict[str, Any]]:
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

    async def _convert_sub_message_to_part(self, sub: Any) -> Optional[Dict[str, Any]]:
        part = None
        if sub.type == schemas_enums.SubMessageType.FILE.value:
            # 只有通过了上述所有过滤条件的子消息，才会触发文件 I/O
            part = await self._process_file_part(sub.content)
        elif sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
            part = None
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
        if db_file.mime_type.startswith("image/") \
                and self.enable_image_with_model and self.model_supports_images:
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

