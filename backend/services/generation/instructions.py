# backend/services/generation/instructions.py
from pydantic import BaseModel, Field
from typing import Optional, Dict

from backend.schemas.enums import MessageStatus, SubMessageType, FileManagementType


class BaseInstruction(BaseModel):
    """所有生成指令的基类。"""
    pass


class CreateSubMessage(BaseInstruction):
    """指令：创建一个新的子消息。

    Manager 必须在发出此指令前预先生成 UUID 并赋值给 sub_message_id。
    """
    sub_message_id: str = Field(..., description="预生成的子消息UUID (原 temp_ref_id)")
    type: str = SubMessageType.NORMAL.value
    sortOrder: int
    status: MessageStatus = MessageStatus.GENERATING
    initial_content: str = ""
    config: Optional[Dict] = None


class AppendToSubMessage(BaseInstruction):
    """指令：向指定的子消息追加内容。"""
    sub_message_id: str = Field(..., description="目标子消息UUID (原 temp_ref_id)")
    content: str


class UpdateSubMessageContent(BaseInstruction):
    """指令：完全替换指定子消息的内容。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    content: str


class UpdateSubMessageStatus(BaseInstruction):
    """指令：更新指定子消息的状态。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    status: MessageStatus


class UpdateSubMessageConfig(BaseInstruction):
    """指令：更新指定子消息的配置项 (Config)。"""
    sub_message_id: str = Field(..., description="目标子消息UUID")
    config: Dict = Field(..., description="新的配置字典")


class SetFinalStatus(BaseInstruction):
    """指令：设置整个生成任务的最终状态。"""
    status: MessageStatus


class UpdateChatName(BaseInstruction):
    """指令：更新指定会话的名称。"""
    chat_id: str
    new_name: str


class PersistFileRecord(BaseInstruction):
    """指令：在数据库中持久化一个文件记录。

    通常在 Manager 处理生成图片等二进制资源时使用。
    Manager 负责 IO 保存，然后发出此指令在 DB 创建记录。
    此指令通常紧随一个引用此 file_id 的 CreateSubMessage 指令。
    """
    file_id: str = Field(..., description="预生成的文件UUID")
    filename: str
    storage_path: str
    mime_type: str
    size: int
    management_type: str = FileManagementType.SUB_MESSAGE.value


class UpdateZipHistorySubMessage(BaseInstruction):
    """指令：创建或更新一个ZipHistory类型的子消息。

    注意：在新的架构中，建议逐步废弃此专用指令，转而使用组合的 Create/Update 指令。
    但为了兼容现有业务逻辑，暂时保留并适配 sub_message_id。
    """
    sub_message_id: str = Field(..., description="预生成的子消息UUID")
    target_message_id: str = Field(..., description="挂载的目标父消息ID")
    content: str
    status: MessageStatus

