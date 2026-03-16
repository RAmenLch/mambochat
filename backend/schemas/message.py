# backend/schemas/message.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
import json

from backend.schemas.enums import MessageRole, MessageStatus, SubMessageType, ToolDecisionType
from backend.schemas.file import File as FileSchema  # 导入文件模型以供类型提示


# --- SubMessage Schemas ---
class McpToolContent(BaseModel):
    """
    专门用于处理 SubMessageType.MCP_TOOL 的 content 字段结构。
    """
    tool_call_id: str
    name: str
    # arguments 可能是 JSON 字符串（来自 LLM 原始输出）或已解析的字典
    arguments: Union[str, Dict[str, Any]]
    input_schema: Optional[Dict[str, Any]] = None
    # 执行结果，None 表示尚未执行
    result: Optional[str] = None
    is_error: bool = False

    @property
    def is_executed(self) -> bool:
        """判断工具是否已执行完成"""
        return self.result is not None

    def get_argument_dict(self) -> Dict[str, Any]:
        """安全地获取参数字典"""
        if isinstance(self.arguments, dict):
            return self.arguments
        try:
            return json.loads(self.arguments)
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_openai_tool_call(self) -> Dict[str, Any]:
        """生成发送给 LLM 的 Assistant tool_calls 部分"""
        # OpenAI 要求 arguments 必须是 JSON 字符串
        if isinstance(self.arguments, str):
            args_str = self.arguments
        else:
            args_str = json.dumps(self.arguments, ensure_ascii=False)

        return {
            "id": self.tool_call_id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": args_str
            }
        }

    def to_openai_tool_result_message(self) -> Optional[Dict[str, Any]]:
        """生成发送给 LLM 的 Role: tool 消息部分"""
        if not self.is_executed:
            return None

        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.result
        }

    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'McpToolContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for McpToolContent: {e}")

class SubMessageConfig(BaseModel):
    is_collapsed: bool = Field(False, description="分区是否折叠")
    is_minimal: bool = Field(False, description="分区是否处于最小化状态")
    context_participation_length: Optional[int] = Field(None,
                                                        description="参加上下文长度: None(默认)-参与; 0-不参与; N>0-在倒数N条内参与")
    zip_enable: Optional[bool] = Field(None, description="【仅用于ZipHistory类型】标记此压缩历史是否已启用")


class SubMessageBase(BaseModel):
    content: str
    type: SubMessageType = Field(SubMessageType.NORMAL, description="分区类型，例如 Normal, Reasoning, File, Usage 等")
    config: SubMessageConfig = Field(default_factory=SubMessageConfig, description="分区的配置项")
    status: MessageStatus = Field(MessageStatus.COMPLETED, description="分区的状态")


class SubMessageCreate(SubMessageBase):
    sortOrder: int = Field(..., description="分区的排序权重")
    id: Optional[str] = Field(None, description="预生成的UUID，如果未提供则自动生成")

class SubMessageUpdate(BaseModel):
    content: Optional[str] = None
    config: Optional[SubMessageConfig] = None
    status: Optional[MessageStatus] = None


class SubMessage(SubMessageBase):
    id: str
    createdAt: datetime
    messageId: str
    sortOrder: int

    # 新增字段，用于在API响应中携带文件详细信息
    file_info: Optional[FileSchema] = Field(None, description="如果分区类型是文件，此字段将包含文件的详细信息")

    @field_validator("config", mode="before")
    @classmethod
    def parse_config_json(cls, v):
        """在验证前，将从数据库读取的JSON字符串解析为字典。"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # 如果数据库中的JSON格式错误，返回一个默认值以避免崩溃
                return {}
        return v

    class Config:
        from_attributes = True


# --- Message Schemas ---

class MessageBase(BaseModel):
    role: MessageRole


class MessageCreate(MessageBase):
    sub_messages: List[SubMessageCreate]


class MessageUpdate(BaseModel):
    """用于更新消息内容并触发重新生成"""
    sub_messages: List[SubMessageCreate]
    resend: bool = Field(False, description="是否删除后续消息并重新生成AI回答")


# noinspection PyDataclass
class Message(MessageBase):
    id: str
    createdAt: datetime
    chatId: str
    sortOrder: int
    sub_messages: List[SubMessage] = Field(default_factory=list)
    status: Optional[MessageStatus] = Field(None,
                                            description="消息的动态计算状态，例如 'generating', 'completed', 'failed'。仅在API响应时填充。")

    class Config:
        from_attributes = True


class EditedAction(BaseModel):
    """编辑后的工具调用动作"""
    name: str = Field(..., description="被编辑的工具名称")
    args: Dict[str, Any] = Field(..., description="编辑后的工具参数")


class ToolDecision(BaseModel):
    """工具调用的用户决策结果"""
    type: ToolDecisionType
    edited_action: Optional[EditedAction] = Field(None, description="编辑后的工具调用参数（仅在 type=edit 时有效）")
    message: Optional[str] = Field(None, description="拒绝原因或其他附加信息")


# 接收前端审核决策的请求模型
class ToolApprovalRequest(BaseModel):
    sub_message_id: str
    decision: ToolDecision

class ReviewToolContent(BaseModel):
    """
    专门用于处理 SubMessageType.REVIEW_TOOL 的 content 字段结构。
    强制要求强类型，拒绝 Union，确保全链路结构化。
    """
    tool_call_id: str
    name: str
    arguments: Dict[str, Any] = Field(..., description="必须是已解析的字典，若上游为JSON字符串需在Decode层完成解析")
    description: Optional[str] = Field(None, description="审核描述说明")
    interrupt_index: int = Field(..., description="中断事件中的序号，用于严格保证多工具并发时的决策数组顺序")
    batch_id: str = Field(..., description="中断批次号")
    decision: Optional[ToolDecision] = Field(None, description="用户的决策结果，None 表示尚未做出决策")
    input_schema: Optional[Dict[str, Any]] = None
    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'ReviewToolContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for ReviewToolContent: {e}")
