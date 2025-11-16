# backend/schemas/enums.py
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class SubMessageType(str, Enum):
    """定义子消息的类型"""
    NORMAL = "Normal"
    REASONING = "Reasoning"
    FILE = "File"
    USAGE = "Usage"


class FileManagementType(str, Enum):
    """定义文件记录的管理类型和生命周期状态"""
    TEMPORARY = "temporary"          # 临时文件，等待与消息关联
    SUB_MESSAGE = "sub_message"      # 已被聊天消息引用的文件
    GLOBAL_SETTING = "global_setting"  # 被全局设置（如头像）引用的文件

