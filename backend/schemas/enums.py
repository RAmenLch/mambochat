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
    ZIP_HISTORY = "ZipHistory"
    MCP_TOOL = "McpTool"


class FileManagementType(str, Enum):
    """定义文件记录的管理类型和生命周期状态"""
    TEMPORARY = "temporary"          # 临时文件，等待与消息关联
    SUB_MESSAGE = "sub_message"      # 已被聊天消息引用的文件
    GLOBAL_SETTING = "global_setting"  # 被全局设置（如头像）引用的文件


class MoveAction(str, Enum):
    """定义节点移动的操作类型"""
    BEFORE = "before"  # 放置在参考节点之前
    AFTER = "after"    # 放置在参考节点之后
    INSIDE = "inside"  # 放置在参考文件夹内部


class ProviderWorkerType(str, Enum):
    """定义服务商使用的 Worker 类型"""
    OPENAI = "openai"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


class ModelType(str, Enum):
    """定义 AI 模型的类型"""
    CHAT = "chat"
    EMBEDDING = "embedding"
