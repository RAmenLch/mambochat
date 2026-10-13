# backend/services/group_chat/runtime.py

"""
群组轮次的轻量运行上下文。由调度器显式构造并传入托管生成层，
不通过 Agent 全局配置或进程可变全局变量传递。

同时提供一个 ContextVar，便于深层工具实现读取当前群上下文
（例如 group_mail_tool_provider 在无法接收显式参数时回退读取）。
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GroupExecutionContext:
    task_id: str
    group_id: str
    member_chat_id: str
    member_alias: str
    assistant_message_id: Optional[str] = None


_current_group_context: ContextVar[Optional[GroupExecutionContext]] = ContextVar(
    "current_group_context", default=None
)


def set_group_context(ctx: Optional[GroupExecutionContext]):
    return _current_group_context.set(ctx)


def reset_group_context(token) -> None:
    _current_group_context.reset(token)


def get_group_context() -> Optional[GroupExecutionContext]:
    return _current_group_context.get()
