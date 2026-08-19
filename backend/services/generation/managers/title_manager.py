# backend/services/generation/managers/title_manager.py

import json
import re
from typing import AsyncGenerator, Optional, Tuple

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import setting_crud
from backend.schemas import SubMessageType
from backend.services.generation.core.instructions import (
    BaseInstruction,
    SetFinalStatus,
    UpdateChatName,
    NotifyUser
)
from backend.services.generation.managers.base_manager import AbstractGenerateManager
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.builders.director import LLMInputDirector


class TitleGenerationContext(BaseModel):
    """标题生成任务的上下文信息"""
    chat_id: str


class TitlePromptProvider:
    """
    标题生成提示词提供者。
    根据全局配置的语言设置，返回对应的 System Prompt 和 Trigger Prompt。
    """
    _PROMPTS = {
        "en": {
            "system": (
                "You are a conversation title generator. "
                "Analyze the following conversation content and generate a concise, precise title "
                "(no more than 12 words). "
                "You MUST submit the final title by calling the `submit_title` tool. "
                "Do not output the title as plain text."
            ),
            "trigger": "Please analyze the conversation above and call the `submit_title` tool to submit the title."
        },
        "zh-CN": {
            "system": (
                "你是一个对话标题生成器。请分析以下对话内容, "
                "为其生成一个简洁、精确、不超过12个字[len(title)<12]的标题。"
                "你必须通过调用 `submit_title` 工具来提交最终标题, 不要以纯文本形式输出标题。"
            ),
            "trigger": "请分析上述对话内容, 并调用 `submit_title` 工具提交标题。"
        }
    }

    @classmethod
    async def get_prompts(cls, db: AsyncSession) -> Tuple[str, str]:
        """
        获取当前语言配置下的提示词。
        :return: (system_prompt, trigger_prompt)
        """
        lang_setting = await setting_crud.get_setting(db, "language")
        language = lang_setting.value if lang_setting else "zh-CN"

        # 默认回退到中文
        prompts = cls._PROMPTS.get(language, cls._PROMPTS["zh-CN"])
        return prompts["system"], prompts["trigger"]


def _build_submit_title_tool() -> StructuredTool:
    """构建提交标题的工具定义。"""
    class SubmitTitleInput(BaseModel):
        title: str = Field(..., description="生成的会话标题")

    def _noop(title: str) -> str:  # pragma: no cover - 不会被实际执行
        return title

    return StructuredTool.from_function(
        func=_noop,
        name="submit_title",
        description="提交最终生成的会话标题",
        args_schema=SubmitTitleInput,
    )


class TitleGenerateManager(AbstractGenerateManager):
    """
    V2 标题生成管理器。
    通过 Tool Call + ReAct Loop 生成会话标题：
    模型调用 `submit_title` 工具提交标题，校验失败时回灌错误驱动自我修正。
    """

    MAX_REACT_ROUNDS = 3
    TITLE_HARD_LIMIT = 50

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.chat_id: Optional[str] = None

    async def _execute_generation(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        self.chat_id = chat_id

        # 1. 获取动态提示词
        system_prompt, trigger_prompt = await TitlePromptProvider.get_prompts(self.db_session)

        # 2. 初始化指挥官
        director = LLMInputDirector(self.db_session, chat_id=chat_id)

        # 3. 配置指挥官
        llm_input = await (
            director
            .force_normal_mode()
            .use_global_model(["title_generation_model_id", "default_model_id"])
            .set_system_prompt(system_prompt)
            .slice_head_tail(head=2, tail=2)
            .limit_sub_message_content(max_length=500)
            .disable_zip_history()
            .filter_sub_message_types(SubMessageType.NORMAL.value)
            .flatten_history_to_single_user_message()
            .append_user_message(trigger_prompt)
            .set_manager_name(TitleGenerateManager.__name__)
            .build()
        )

        # 绑定工具（不再使用 JSON 模式，改用 Tool Call）
        llm_input.agent_config.tools = [_build_submit_title_tool()]
        llm_input.agent_config.llm_config.parameters['stream'] = False

        # 4. ReAct Loop
        fallback_title: Optional[str] = None

        for _ in range(self.MAX_REACT_ROUNDS):
            accumulated_content = ""
            tool_call: Optional[dict] = None
            # 流式 tool_call 分片聚合缓冲：{index: {id, name, arguments}}
            tc_buffers: dict = {}

            async for mode, event in worker.generate(llm_input):
                decoder = worker.resolve_decoder(event)
                text_chunk = decoder.get_text_content(mode, event)
                if text_chunk:
                    accumulated_content += text_chunk

                # 直接从 event 读取 tool_call（不走共享 decoder，避免污染普通对话流程）
                if isinstance(event, (AIMessage, AIMessageChunk)):
                    # 已完成聚合的 tool_calls（非流式 / 完整消息）
                    if event.tool_calls:
                        extracted = self._extract_submit_title_call(event.tool_calls)
                        if extracted and extracted.get("args"):
                            tool_call = extracted
                    # 流式分片：累积到 buffer
                    chunks = getattr(event, "tool_call_chunks", None)
                    if chunks:
                        self._merge_tool_call_chunks(tc_buffers, chunks)

            # 若整轮未拿到完整 tool_call，则从分片 buffer 重建
            if not tool_call and tc_buffers:
                rebuilt = self._rebuild_tool_call_from_chunks(tc_buffers)
                if rebuilt:
                    tool_call = rebuilt

            # 从本轮文本中尝试提取兜底标题（无论是否走工具）
            candidate = self._extract_title_from_text(accumulated_content)
            if candidate:
                fallback_title = candidate

            # 情况一：模型调用了 submit_title
            if tool_call:
                title = self._sanitize_title(tool_call.get("args", {}).get("title"))
                if title:
                    yield UpdateChatName(chat_id=self.chat_id, new_name=title)
                    yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)
                    return
                # 校验失败：回灌错误，进入下一轮
                err_msg = "标题为空或全为空白字符，请重新生成并调用 submit_title 工具提交。"
                llm_input.context.messages.extend(self._tool_round_messages(tool_call, err_msg))
                continue

            # 情况二：模型未调用工具，但文本中可提取到标题 → 直接采用（降级）
            if fallback_title:
                yield UpdateChatName(chat_id=self.chat_id, new_name=fallback_title)
                yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)
                return

            # 情况三：既无工具调用也无文本 → 回灌提示，进入下一轮
            llm_input.context.messages.append({
                "role": "user",
                "content": "你没有调用 submit_title 工具。请分析对话内容，调用 submit_title 工具提交标题。",
            })

        # ReAct 轮次用尽：若曾有兜底候选则采用，否则失败
        if fallback_title:
            yield UpdateChatName(chat_id=self.chat_id, new_name=fallback_title)
            yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)
        else:
            yield self._create_error_notification("模型在限定轮次内未能生成有效标题")
            yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

    # ── 辅助方法 ──────────────────────────────────────────

    def _extract_submit_title_call(self, tool_calls: list) -> Optional[dict]:
        """从 tool_calls 列表中找出 submit_title 调用，兼容 OpenAI function 包装与 LangChain 标准格式。"""
        for tc in tool_calls:
            name = tc.get("name") or (tc.get("function") or {}).get("name")
            if name != "submit_title":
                continue
            if "function" in tc:
                args = tc["function"].get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                return {"id": tc.get("id"), "args": args if isinstance(args, dict) else {}}
            return {"id": tc.get("id"), "args": tc.get("args") or {}}
        return None

    def _merge_tool_call_chunks(self, buffers: dict, tool_calls: list) -> None:
        """将流式 tool_call 分片按 index 聚合到 buffers。

        LangChain tool_call_chunks 格式: {"name": ..., "args": str增量, "id": ..., "index": ...}
        OpenAI function 增量格式: {"function": {"name":..., "arguments": str增量}, "id":..., "index"/"type"}
        """
        for pos, tc in enumerate(tool_calls):
            idx = tc.get("index", pos)
            buf = buffers.setdefault(idx, {"id": None, "name": "", "arguments": ""})

            if tc.get("id"):
                buf["id"] = tc["id"]

            if "function" in tc:
                fn = tc["function"] or {}
                if fn.get("name"):
                    buf["name"] = fn["name"]
                args = fn.get("arguments")
                if isinstance(args, str):
                    buf["arguments"] += args
            else:
                if tc.get("name"):
                    buf["name"] = tc["name"]
                args = tc.get("args")
                if isinstance(args, str):
                    buf["arguments"] += args
                elif isinstance(args, dict):
                    buf["arguments"] += json.dumps(args, ensure_ascii=False)

    def _rebuild_tool_call_from_chunks(self, buffers: dict) -> Optional[dict]:
        """从聚合的分片 buffer 重建 submit_title 调用。"""
        for buf in buffers.values():
            if buf.get("name") != "submit_title":
                continue
            args_str = buf.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            return {"id": buf.get("id"), "args": args if isinstance(args, dict) else {}}
        return None

    def _sanitize_title(self, raw: Optional[str]) -> Optional[str]:
        """清洗标题：压缩空白/换行，超长截断。返回 None 表示无效。"""
        if not isinstance(raw, str):
            return None
        title = re.sub(r"\s+", " ", raw).strip()
        if not title:
            return None
        return title[: self.TITLE_HARD_LIMIT]

    def _extract_title_from_text(self, text: str) -> Optional[str]:
        """从纯文本输出中兜底提取标题。"""
        if not text or not text.strip():
            return None
        # 优先提取 JSON 中的 title 字段
        m = re.search(r'\{[^{}]*"title"\s*:\s*"([^"]+)"[^{}]*\}', text)
        if m:
            return self._sanitize_title(m.group(1))
        # 否则取首个非空行
        for line in text.splitlines():
            line = line.strip().strip('`').strip()
            if line:
                return self._sanitize_title(line)
        return None

    def _tool_round_messages(self, tool_call: dict, error_content: str) -> list:
        """构建一轮 ReAct 的 assistant(tool_calls) + tool 消息对，用于回灌错误。"""
        args = tool_call.get("args") or {}
        tc_id = tool_call.get("id") or "call_submit_title"
        return [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": "submit_title", "arguments": json.dumps(args, ensure_ascii=False)},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "name": "submit_title",
                "content": error_content,
            },
        ]

    def _create_error_notification(self, message: str) -> NotifyUser:
        """辅助方法：创建错误通知指令"""
        return NotifyUser(
            category="title_generation_error",
            context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
            level="error",
            message=message
        )

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas.enums.MessageStatus,
            exception: Optional[Exception] = None,
            chat_id: Optional[str] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        异常清理逻辑：发送全局通知。
        """
        if exception:
            print(f"生成标题时发生系统异常: {str(exception)}")
            yield self._create_error_notification(f"生成标题时发生系统异常: {str(exception)}")
