# backend/services/generation/core/context.py

from pydantic import BaseModel, Field


class BaseNotificationContext(BaseModel):
    """
    所有全局通知上下文的基类。
    用于 NotifyUser 指令的泛型约束。
    """
    pass


class TitleGenerationContext(BaseNotificationContext):
    """
    标题生成任务的上下文信息。
    当标题生成失败或成功时，随通知一起发送给前端，以便前端定位具体的会话。
    """
    chat_id: str = Field(..., description="发生事件的会话 ID")
    failed_step: str = Field(default="unknown", description="失败的具体步骤（如适用）")


class ZipHistoryContext(BaseNotificationContext):
    """
    历史压缩任务的上下文信息。
    """
    chat_id: str = Field(..., description="会话 ID")
    target_message_id: str = Field(..., description="触发压缩的目标消息 ID")


class ToolExecutionErrorContext(BaseNotificationContext):
    """
    工具执行异常的上下文信息。
    用于向用户反馈 MCP 工具或本地工具的调用失败详情。
    """
    tool_name: str = Field(..., description="发生错误的工具名称")
    tool_call_id: str = Field(..., description="工具调用的唯一 ID")
    error_details: str = Field(..., description="详细的错误堆栈或提示")

