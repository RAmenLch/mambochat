# backend/services/generation/instructions.py
from pydantic import BaseModel
from typing import Optional, Dict

from backend.schemas.enums import MessageStatus, SubMessageType

class BaseInstruction(BaseModel):
    """所有生成指令的基类。"""
    pass

class CreateSubMessage(BaseInstruction):
    """指令：创建一个新的子消息。

    temp_ref_id: 临时引用ID，用于Manager内部映射到实际的sub_message_id。
                 例如，"main_content" 或 "reasoning_content"。
    type: 子消息类型，例如 "Normal" 或 "Reasoning"。
    sortOrder: 子消息在父消息中的排序顺序。
    status: 子消息的初始状态。
    initial_content: 首次创建时可能包含的初始内容。
    config: 子消息的配置项。
    """
    temp_ref_id: str
    type: str = SubMessageType.NORMAL.value
    sortOrder: int
    status: MessageStatus = MessageStatus.GENERATING
    initial_content: str = ""
    config: Optional[Dict] = None

class AppendToSubMessage(BaseInstruction):
    """指令：向指定的子消息追加内容。

    temp_ref_id: 临时引用ID，指示要追加到哪个子消息。
    content: 要追加的文本内容。
    """
    temp_ref_id: str
    content: str

class UpdateSubMessageContent(BaseInstruction):
    """指令：完全替换指定子消息的内容。

    temp_ref_id: 临时引用ID，指示要更新哪个子消息。
    content: 新的完整内容。
    """
    temp_ref_id: str
    content: str

class UpdateSubMessageStatus(BaseInstruction):
    """指令：更新指定子消息的状态。

    temp_ref_id: 临时引用ID，指示要更新哪个子消息的状态。
    status: 子消息的新状态。
    """
    temp_ref_id: str
    status: MessageStatus

class SetFinalStatus(BaseInstruction):
    """指令：设置整个生成任务的最终状态。

    status: 整个生成任务的最终状态。
    """
    status: MessageStatus

class UpdateChatName(BaseInstruction):
    """指令：更新指定会话的名称。"""
    chat_id: str
    new_name: str

class UpdateZipHistorySubMessage(BaseInstruction):
    """指令：创建或更新一个ZipHistory类型的子消息。"""
    target_message_id: str
    content: str
    status: MessageStatus
