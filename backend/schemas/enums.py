# backend/schemas/enums.py
from enum import Enum


class ChatMode(str, Enum):
    """定义会话的模式"""
    NORMAL = "normal"
    AGENT = "agent"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING_REVIEW = "pending_review"


class SubMessageType(str, Enum):
    """定义子消息的类型"""
    NORMAL = "Normal"
    REASONING = "Reasoning"
    FILE = "File"
    USAGE = "Usage"
    ZIP_HISTORY = "ZipHistory"
    MCP_TOOL = "McpTool"
    SUGGEST = "Suggest"
    REVIEW_TOOL = "ReviewTool"
    ASK_USER = "AskUser"
    ERROR = "Error"


class FileManagementType(str, Enum):
    """定义文件记录的管理类型和生命周期状态"""
    TEMPORARY = "temporary"          # 临时文件，等待与消息关联
    SUB_MESSAGE = "sub_message"      # 已被聊天消息引用的文件
    GLOBAL_SETTING = "global_setting"  # 被全局设置（如头像）引用的文件
    KB_DOCUMENT = "kb_document"      # 旧版知识库文件（保留用于兼容）
    RESOURCE = "resource"            # 通用资源文件，统一管理所有上传到资源中心的文件
    AGENT_AVATAR = "agent_avatar"

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
    ANTHROPIC = "anthropic"


class ModelType(str, Enum):
    """定义 AI 模型的类型"""
    CHAT = "chat"
    EMBEDDING = "embedding"


# --- Resource Enums ---

class ResourceItemType(str, Enum):
    """定义资源项目的基本类型"""
    RESOURCE = "resource"
    FOLDER = "folder"


class ResourceType(str, Enum):
    """定义具体的资源业务类型"""
    KNOWLEDGE_BASE = "knowledge_base"
    SYSTEM_PROMPT = "system_prompt"
    SUBMESSAGE_TEMPLATE = "submessage_template"
    KB_FILE = "kb_file"  # 旧版知识库文件类型（保留用于兼容）
    FILE = "file"        # 通用文件资源类型，支持向量化
    SKILL = "skill"

class KBFileStatus(str, Enum):
    """定义知识库文件的整体处理状态"""
    INITIAL = "INITIAL"      # 初始状态，未处理
    CLEANING = "CLEANING"    # 正在清理旧数据
    READING = "READING"      # 正在读取文件
    SPLITTING = "SPLITTING"  # 正在切分文本
    EMBEDDING = "EMBEDDING"  # 正在进行向量化 (原 PROCESSING)
    COMPLETED = "COMPLETED"  # 处理完成 (原 INDEXED)
    FAILED = "FAILED"        # 处理失败
    STOPPED = "STOPPED"      # 任务已停止


class McpTransportType(str, Enum):
    """定义 MCP 服务器的传输类型"""
    STDIO = "stdio"
    SSE = "sse"

class ToolReviewMode(str, Enum):
    NONE = "none"
    REQUIRE_REVIEW = "require_review"


class ToolStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"

class ToolDecisionType(str, Enum):
    """工具调用审核的决策类型"""
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"

class AgentItemType(str, Enum):
    """定义 Agent 树状目录结构中的节点类型"""
    AGENT = "agent"
    FOLDER = "folder"


class AgentTypeEnum(str, Enum):
    """定义 Agent 初始化的类型标识符"""
    REACT = "ReActAgent"
    DEEP = "DeepAgent"
    MAMBO = "Mambo"

class BackendType(str, Enum):
    """定义 Backend 的类型"""
    SSH = "ssh"
    API = "api"