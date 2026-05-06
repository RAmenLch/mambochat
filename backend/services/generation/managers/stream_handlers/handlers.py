import json
from typing import AsyncGenerator
from langchain_core.messages import AIMessage

from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import ReviewToolContent, AskUserContent
from backend.services.generation.core.instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage,
    UpdateSubMessageConfig, UpdateSubMessageStatus,
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
                    tool_call_id = reviewable_calls[idx].get("id") if idx < len(reviewable_calls) else (action_req.get("id") or generate_uuid())
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
            for call in middleware_data.get("approved_calls", []):
                name = call.get("name")
                for provider in context.providers:
                    if provider.matches_tool_name(name):
                        async for inst in provider.create_call_instruction(call.get("id"), name, call.get("args") or {}, context.tool_map.get(name)):
                            yield inst
                        break

            for res in middleware_data.get("rejected_results", []):
                name = res.get("name")
                for provider in context.providers:
                    if provider.matches_tool_name(name):
                        async for inst in provider.create_call_instruction(res.get("id"), name, {}, context.tool_map.get(name)):
                            yield inst
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
                if has_hitl: continue
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
                async for inst in self._handle_image(url, context.created_stream_ids):
                    yield inst

        # 2. 用量统计
        usage_data = context.decode.get_usage(context.mode, context.event)
        if usage_data:
            context.final_usage_data.update(usage_data)

    async def _handle_image(self, base64_url: str, created_ids: set) -> AsyncGenerator[BaseInstruction, None]:
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
            content_ids = [sid for sid in created_ids if sid.endswith('-N')]
            if content_ids:
                yield AppendToSubMessage(sub_message_id=content_ids[-1], content=f"\n\n**处理生成图片时出错: {e}**")
