# backend/services/generation/core/instructions.py

from pydantic import BaseModel, Field
from typing import Optional, Dict, Generic, TypeVar

from backend.schemas.enums import MessageStatus, SubMessageType, FileManagementType


class BaseInstruction(BaseModel):
    """所有生成指令的抽象基类。"""
    pass


class InterruptGeneration(BaseInstruction):
    """
    指令：立即中断生成循环 (Control Flow)。
    当 Manager 收到此指令时，应停止接收 Worker 的后续事件并进入 finalize 流程。
    此指令通常由 Manager 内部消费，不应传递给 Executor。
    """
    pass


class CreateSubMessage(BaseInstruction):
    """指令：创建一个新的子消息。"""
    sub_message_id: str = Field(..., description="预生成的子消息UUID")
    type: str = SubMessageType.NORMAL.value
    sortOrder: int
    status: MessageStatus = MessageStatus.GENERATING
    initial_content: str = ""
    config: Optional[Dict] = None


class AppendToSubMessage(BaseInstruction):
    """指令：向指定的流式子消息追加文本内容。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    content: str


class UpdateSubMessageContent(BaseInstruction):
    """指令：完全替换指定子消息的内容 (非流式更新)。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    content: str


class UpdateSubMessageStatus(BaseInstruction):
    """指令：更新指定子消息的状态 (如从 GENERATING 变为 COMPLETED)。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    status: MessageStatus


class UpdateSubMessageConfig(BaseInstruction):
    """指令：更新指定子消息的配置项字典。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    config: Dict = Field(..., description="新的配置字典")


class SetFinalStatus(BaseInstruction):
    """指令：设置整个生成任务 (父消息) 的最终状态。"""
    status: MessageStatus


class UpdateChatName(BaseInstruction):
    """指令：更新指定会话的名称。"""
    chat_id: str
    new_name: str


T = TypeVar('T', bound=BaseModel)

class NotifyUser(BaseInstruction, Generic[T]):
    """
    指令：向前端发送全局通知 (如错误提示、系统警告)。
    使用泛型设计以支持类型安全的上下文传递。
    """
    category: str = Field(..., description="业务事件分类，例如 'title_generation_error'")
    context: T = Field(..., description="结构化的上下文数据模型，必须继承自 BaseModel")
    level: str = Field(..., description="通知级别，例如 'error', 'warning', 'info'")
    message: str = Field(..., description="显示给用户的详细错误或提示信息")


class SaveAndPersistFile(BaseInstruction):
    """
    指令：保存物理文件并在数据库创建记录。
    通常在 Worker 生成图片等二进制资源后使用。
    """
    file_id: str = Field(..., description="预生成的文件UUID")
    filename: str
    base64_data: str = Field(..., description="文件的Base64编码字符串（不含Header）")
    mime_type: str
    management_type: str = FileManagementType.SUB_MESSAGE.value


class UpdateZipHistorySubMessage(BaseInstruction):
    """
    指令：创建或更新一个 ZipHistory 类型的子消息。
    专属业务指令，用于对话历史压缩场景。
    """
    sub_message_id: str = Field(..., description="预生成的子消息UUID")
    target_message_id: str = Field(..., description="挂载的目标父消息ID")
    content: str
    status: MessageStatus
