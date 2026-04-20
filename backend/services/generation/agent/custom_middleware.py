from typing import Any, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage


class ToolMessageOrderingMiddleware(AgentMiddleware):
    """Middleware to ensure ToolMessages are ordered to match the AIMessage tool_calls order."""

    def _reorder_tool_messages(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        """Reorder ToolMessages to match the order of tool_calls in the preceding AIMessage."""
        if not messages:
            return messages

        new_messages: list[AnyMessage] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            new_messages.append(msg)
            i += 1

            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_call_order = {
                    tc["id"]: idx for idx, tc in enumerate(msg.tool_calls)
                }

                tool_msgs: list[ToolMessage] = []
                while i < len(messages) and isinstance(messages[i], ToolMessage):
                    tool_msgs.append(messages[i])
                    i += 1

                tool_msgs.sort(
                    key=lambda m: tool_call_order.get(m.tool_call_id, float("inf"))
                )
                new_messages.extend(tool_msgs)

        return new_messages

    def wrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        reordered_messages = self._reorder_tool_messages(request.messages)

        # 同步更新 state 中的 messages，确保下一次循环历史记录正确
        # ModelRequest.state 类型为 AgentState[Any]（TypedDict），始终为 dict
        request.state["messages"] = reordered_messages

        # 通过 override 创建新的 request，覆盖 messages 属性
        sorted_request = request.override(messages=reordered_messages)

        return handler(sorted_request)

    async def awrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        reordered_messages = self._reorder_tool_messages(request.messages)

        # 同步更新 state 中的 messages，确保下一次循环历史记录正确
        # ModelRequest.state 类型为 AgentState[Any]（TypedDict），始终为 dict
        request.state["messages"] = reordered_messages

        # 通过 override 创建新的 request，覆盖 messages 属性
        sorted_request = request.override(messages=reordered_messages)

        return await handler(sorted_request)
