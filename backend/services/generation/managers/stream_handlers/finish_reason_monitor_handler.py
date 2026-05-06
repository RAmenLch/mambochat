# backend/services/generation/managers/stream_handlers/finish_reason_monitor_handler.py

from typing import AsyncGenerator

from langchain_core.messages import AIMessage

from backend.services.generation.core.instructions import BaseInstruction
from backend.services.generation.managers.stream_handlers.base_handler import BaseStreamHandler, StreamContext
from backend.services.generation.managers.stream_handlers.finish_reason_classifier import FinishReasonClassifier


class FinishReasonMonitorHandler(BaseStreamHandler):
    """
    被动监控 finish_reason 的 Handler。
    不中断生成流程，仅在 updates 模式下从 AIMessage 的 response_metadata 中
    提取 finish_reason 并写入 StreamContext，供 Manager 在 finalization 阶段读取。
    采用 last-wins 策略：每轮 AIMessage 都会覆盖 context.last_finish_reason，
    最终保留的是最后一轮的 finish_reason。
    """

    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        if context.mode == "updates" and isinstance(context.event, AIMessage):
            metadata = getattr(context.event, "response_metadata", None)
            reason = FinishReasonClassifier.extract_from_metadata(metadata)
            if reason:
                context.last_finish_reason = reason
        if False:
            yield
