import json
import traceback
from typing import AsyncGenerator, List, Dict, Any
from langchain_core.messages import AIMessage, ToolMessage

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import ErrorContent, ReviewToolContent, AskUserContent, TaskSubStepContent, SecurityReviewContent
from backend.services.generation.core.instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage,
    UpdateSubMessageConfig, UpdateSubMessageStatus, UpdateSubMessageContent,
    SaveAndPersistFile, InterruptGeneration
)
from backend.services.generation.managers.stream_handlers.base_handler import BaseStreamHandler, StreamContext
from backend.services.generation.managers.stream_handlers.finish_reason_monitor_handler import FinishReasonMonitorHandler


class HitlHandler(BaseStreamHandler):
    """处理人机交互 (HITL) 的中断与恢复"""
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        Decode = context.decode

        # 1. 拦截中断请求
        interrupt_data = Decode.get_hitl_interrupt(context.mode, context.event)
        if interrupt_data:
            # --- ask_user 类型中断 ---
            if interrupt_data.get("type") == "ask_user":
                questions = interrupt_data.get("questions", [])
                tool_call_id = interrupt_data.get("tool_call_id", "")
                current_batch_id = generate_uuid()

                # 创建 McpTool 子消息（记录工具调用信息，参与上下文）
                pending_call = next(
                    (tc for tc in context.pending_hitl_tool_calls if tc.get("id") == tool_call_id),
                    None
                )
                if pending_call:
                    for provider in context.providers:
                        if provider.matches_tool_name("ask_user"):
                            async for inst in provider.create_call_instruction(
                                tool_call_id, "ask_user", pending_call.get("args") or {},
                                context.tool_map.get("ask_user")
                            ):
                                yield inst
                            break

                # 创建 AskUser 子消息（展示提问 UI）
                ask_content = AskUserContent(
                    tool_call_id=tool_call_id,
                    questions=questions,
                    answers=None,
                    interrupt_index=0,
                    batch_id=current_batch_id,
                )
                yield CreateSubMessage(
                    sub_message_id=generate_uuid(),
                    type=schemas_enums.SubMessageType.ASK_USER.value,
                    sortOrder=2,
                    status=schemas_enums.MessageStatus.PENDING_REVIEW,
                    initial_content=ask_content.to_json_string(),
                    config={"context_participation_length": 0}
                )
                yield InterruptGeneration()
                return

            # --- HITL 审核中断 ---
            if "action_requests" in interrupt_data:
                current_batch_id = generate_uuid()
                reviewable_calls = [tc for tc in context.pending_hitl_tool_calls if context.hitl_config.get(tc.get("name"))]

                for idx, action_req in enumerate(interrupt_data["action_requests"]):
                    # 优先使用中断消息自带的 tool_call_id（security_review 中间件的 ActionRequest.tool_call_id）
                    tool_call_id = action_req.get("tool_call_id")
                    if not tool_call_id and idx < len(reviewable_calls):
                        # 回退：按 index 从 pending 列表中取（兼容 deepagents 等不提供该字段的中间件）
                        tool_call_id = reviewable_calls[idx].get("id")
                    if not tool_call_id:
                        tool_call_id = generate_uuid()
                    name = action_req.get("name")
                    target_tool = context.tool_map.get(name)

                    review_content = ReviewToolContent(
                        tool_call_id=tool_call_id,
                        name=name,
                        arguments=action_req.get("args", {}),
                        input_schema=target_tool.args if target_tool else None,
                        description=action_req.get("description"),
                        interrupt_index=idx,
                        batch_id=current_batch_id,
                        decision=None
                    )

                    yield CreateSubMessage(
                        sub_message_id=generate_uuid(),
                        type=schemas_enums.SubMessageType.REVIEW_TOOL.value,
                        sortOrder=2,
                        status=schemas_enums.MessageStatus.PENDING_REVIEW,
                        initial_content=review_content.to_json_string(),
                        config={"context_participation_length": 0}
                    )
                yield InterruptGeneration()
                return

        # 2. 处理恢复数据
        middleware_data = Decode.get_hitl_middleware_data(context.mode, context.event)
        if middleware_data:
            # MCP_TOOL 子消息已由 ToolExecutionHandler 创建，此处不再重复创建 create_call_instruction；
            # 仅对 rejected 工具调用 create_result_instruction 写入拒绝原因
            for res in middleware_data.get("rejected_results", []):
                name = res.get("name")
                for provider in context.providers:
                    if provider.matches_tool_name(name):
                        async for inst in provider.create_result_instruction(res.get("id"), res.get("content"), True):
                            yield inst
                        break


class TextAndReasoningHandler(BaseStreamHandler):
    """处理正文与推理内容的流式输出"""
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        if not context.lc_run_uuid:
            return

        # 1. 正文
        text_content = context.decode.get_text_content(context.mode, context.event)
        if text_content:
            content_id = f"{context.lc_run_uuid}-N"
            if content_id not in context.created_stream_ids:
                context.created_stream_ids.add(content_id)
                yield CreateSubMessage(sub_message_id=content_id, type=schemas_enums.SubMessageType.NORMAL.value, sortOrder=1)
            yield AppendToSubMessage(sub_message_id=content_id, content=text_content)

        # 2. 推理
        reasoning_content = context.decode.get_reasoning_content(context.mode, context.event)
        if reasoning_content:
            reasoning_id = f"{context.lc_run_uuid}-R"
            if reasoning_id not in context.created_stream_ids:
                context.created_stream_ids.add(reasoning_id)
                yield CreateSubMessage(
                    sub_message_id=reasoning_id, type=schemas_enums.SubMessageType.REASONING.value,
                    sortOrder=0, config={"is_minimal": True}
                )
            yield AppendToSubMessage(sub_message_id=reasoning_id, content=reasoning_content)


class RoundClosureHandler(BaseStreamHandler):
    """处理轮次闭合 (当 updates 模式的 AIMessage 到达时)"""
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        if context.mode == "updates" and isinstance(context.event, AIMessage) and context.lc_run_uuid:
            reasoning_id = f"{context.lc_run_uuid}-R"
            content_id = f"{context.lc_run_uuid}-N"

            if reasoning_id in context.created_stream_ids:
                yield UpdateSubMessageConfig(sub_message_id=reasoning_id, config={"is_minimal": True})
                yield UpdateSubMessageStatus(sub_message_id=reasoning_id, status=schemas_enums.MessageStatus.COMPLETED)
                context.created_stream_ids.discard(reasoning_id)

            if content_id in context.created_stream_ids:
                yield UpdateSubMessageStatus(sub_message_id=content_id, status=schemas_enums.MessageStatus.COMPLETED)
                context.created_stream_ids.discard(content_id)


class ToolExecutionHandler(BaseStreamHandler):
    """处理工具调用与结果"""
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        # 1. 工具调用
        tool_calls = context.decode.get_toolcall_content(context.mode, context.event)
        if tool_calls:
            has_hitl = any(context.hitl_config.get(tc.get("name")) for tc in tool_calls)
            if has_hitl:
                context.pending_hitl_tool_calls.extend(tool_calls)

            for tc in tool_calls:
                name = tc.get("name")
                for provider in context.providers:
                    if provider.matches_tool_name(name):
                        async for inst in provider.create_call_instruction(tc.get("id"), name, tc.get("args") or {}, context.tool_map.get(name)):
                            yield inst
                        break

        # 2. 工具结果
        tool_result = context.decode.get_toolcall_result(context.mode, context.event)
        if tool_result:
            for provider in context.providers:
                async for inst in provider.create_result_instruction(tool_result.get("id"), tool_result.get("text"), tool_result.get("is_error", False)):
                    yield inst


class ImageAndUsageHandler(BaseStreamHandler):
    """处理图片生成和用量统计"""
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        # 1. 图片
        image_data = context.decode.get_image_url(context.mode, context.event)
        if image_data:
            url = image_data.get("image_url", {}).get("url")
            if url and url.startswith("data:image"):
                async for inst in self._handle_image(url):
                    yield inst

        # 2. 用量统计
        usage_data = context.decode.get_usage(context.mode, context.event)
        if usage_data:
            context.final_usage_data.update(usage_data)

    async def _handle_image(self, base64_url: str) -> AsyncGenerator[BaseInstruction, None]:
        try:
            header, encoded_data = base64_url.split(',', 1) if ',' in base64_url else ("data:image/png;", base64_url)
            mime_type = header.split(';')[0].split(':')[1]
            file_id, sub_id = generate_uuid(), generate_uuid()

            yield SaveAndPersistFile(
                file_id=file_id, filename=f"generated_image.{mime_type.split('/')[-1]}",
                base64_data=encoded_data, mime_type=mime_type
            )
            yield CreateSubMessage(
                sub_message_id=sub_id, type=schemas_enums.SubMessageType.FILE.value,
                sortOrder=2, status=schemas_enums.MessageStatus.COMPLETED, initial_content=file_id
            )
        except Exception as e:
            error_content = ErrorContent(
                message=f"处理生成图片时出错: {e}",
                stack_trace=traceback.format_exc()
            )
            yield CreateSubMessage(
                sub_message_id=generate_uuid(),
                type=schemas_enums.SubMessageType.ERROR.value,
                sortOrder=97,
                status=schemas_enums.MessageStatus.COMPLETED,
                initial_content=error_content.to_json_string(),
                config={"context_participation_length": 0}
            )


class SubAgentEventHandler(BaseStreamHandler):
    """处理子代理内部流式事件（custom stream 中的 subagent_event）。

    每个 subagent_event 来自 mambo_agents 的 SubAgentMiddleware，
    携带子代理的推理、文本生成、工具调用和工具结果。
    所有子消息标记 config.task_group_id（= tool_call_id）+ context_participation_length=0，
    前端据此分组并排除出上下文。
    """

    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        if context.mode != "subagent_event":
            return

        event_data: dict = context.event
        tool_call_id: str = event_data["tool_call_id"]
        subagent_type: str = event_data["subagent_type"]
        chunk: dict = event_data["chunk"]  # {"agent": {...}} 或 {"tools": {...}}

        counter = context.subagent_step_counters.get(tool_call_id, 0)
        instructions, counter = self._build_instructions(chunk, tool_call_id, subagent_type, counter)

        for inst in instructions:
            yield inst

        context.subagent_step_counters[tool_call_id] = counter

    def _build_instructions(
        self, chunk: dict, tool_call_id: str, subagent_type: str, start_counter: int
    ) -> tuple:
        """解析 updates 粒度 chunk → (指令列表, 新counter)。"""
        instructions: list = []
        idx = start_counter

        if "model" in chunk:
            for msg in chunk["model"].get("messages", []):
                if not isinstance(msg, AIMessage):
                    continue

                # 推理内容
                reasoning = msg.additional_kwargs.get("reasoning_content")
                if reasoning:
                    idx += 1
                    step = TaskSubStepContent(
                        tool_call_id=tool_call_id,
                        subagent_type=subagent_type,
                        display_type="reasoning",
                        content=reasoning if isinstance(reasoning, str) else str(reasoning),
                        step_order=idx,
                    )
                    instructions.append(self._make_create(step.to_json_string(), idx, tool_call_id,
                                                          config_extra={"is_minimal": True}))

                # 文本正文
                text = msg.content
                if isinstance(text, str) and text.strip():
                    idx += 1
                    step = TaskSubStepContent(
                        tool_call_id=tool_call_id,
                        subagent_type=subagent_type,
                        display_type="text",
                        content=text.strip(),
                        step_order=idx,
                    )
                    instructions.append(self._make_create(step.to_json_string(), idx, tool_call_id))

                # 工具调用
                for tc in msg.tool_calls or []:
                    idx += 1
                    name = tc.get("name", "")
                    args = tc.get("args", {})
                    step = TaskSubStepContent(
                        tool_call_id=tool_call_id,
                        subagent_type=subagent_type,
                        display_type="tool_call",
                        content="",
                        tool_name=name,
                        tool_args=args if isinstance(args, dict) else {},
                        step_order=idx,
                    )
                    instructions.append(self._make_create(step.to_json_string(), idx, tool_call_id))

        if "tools" in chunk:
            for msg in chunk["tools"].get("messages", []):
                if not isinstance(msg, ToolMessage):
                    continue
                idx += 1
                result_text = str(msg.content) if msg.content else ""
                step = TaskSubStepContent(
                    tool_call_id=tool_call_id,
                    subagent_type=subagent_type,
                    display_type="tool_result",
                    content=result_text,
                    tool_name=msg.name or "",
                    step_order=idx,
                )
                instructions.append(self._make_create(step.to_json_string(), idx, tool_call_id))

        return instructions, idx

    @staticmethod
    def _make_create(
        content: str,
        sort_order: int,
        task_group_id: str,
        config_extra: dict | None = None,
    ) -> CreateSubMessage:
        config: Dict[str, Any] = {
            "task_group_id": task_group_id,
            "context_participation_length": 0,
        }
        if config_extra:
            config.update(config_extra)
        return CreateSubMessage(
            sub_message_id=generate_uuid(),
            type=schemas_enums.SubMessageType.TASK_SUBSTEP.value,
            sortOrder=3,
            status=schemas_enums.MessageStatus.COMPLETED,
            initial_content=content,
            config=config,
        )


class SecurityReviewHandler(BaseStreamHandler):
    """处理 AI 安全审核通过事件（custom stream 中的 security_review_passed）。

    当 AutoSecurityReviewMiddleware 判定工具调用安全、自动放行时，
    SecurityReviewPassedEvent 通过 get_stream_writer() 发射 custom 事件。
    此 Handler 将其转为 SubMessageType.SECURITY_REVIEW 存入 DB，
    前端据此展示 AI 审核标记并与对应 McpTool 按钮绑定。
    """
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        if context.mode != "security_review":
            return

        event_data: dict = context.event
        event_type: str = event_data.get("type", "")
        content = SecurityReviewContent(
            tool_call_id=event_data["tool_call_id"],
            tool_name=event_data["tool_name"],
            risk_level=event_data["risk_level"],
            reason=event_data["reason"],
            passed=(event_type == "security_review_passed"),
        )
        yield CreateSubMessage(
            sub_message_id=generate_uuid(),
            type=schemas_enums.SubMessageType.SECURITY_REVIEW.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.COMPLETED,
            initial_content=content.to_json_string(),
            config={"context_participation_length": 0},
        )
