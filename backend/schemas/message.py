# backend/schemas/message.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Union, Dict, Any, Literal
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
    target_sub_msg_id: Optional[str] = Field(None, description="【仅用于ZipHistory类型】子消息粒度的目标子消息ID")
    auto_summary: Optional[bool] = Field(None, description="【仅用于ZipHistory类型】是否为自动摘要（True=自动，None/False=手动）")
    task_group_id: Optional[str] = Field(None, description="【仅用于TaskSubStep类型】子代理任务分组键（= 主代理 task tool_call_id）")


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
    parentId: Optional[str] = Field(None, description="父消息ID，如果不传则自动挂载到当前活跃路径的叶子节点")


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

    # 新增树状结构与分支路由相关字段
    parentId: Optional[str] = Field(None, description="父消息ID")
    lastActiveAt: datetime = Field(..., description="最后活跃时间")
    sibling_ids: List[str] = Field(default_factory=list, description="同级分支的消息ID列表(按创建时间排序)")
    sibling_index: int = Field(0, description="当前消息在同级分支中的索引(从0开始)")

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

class ErrorContent(BaseModel):
    """
    专门用于处理 SubMessageType.ERROR 的 content 字段结构。
    包含简短错误信息和完整的堆栈跟踪。
    """
    message: str = Field(..., description="简短的错误提示信息")
    stack_trace: str = Field(default="", description="完整的错误堆栈信息")

    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'ErrorContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for ErrorContent: {e}")


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


class SecurityReviewContent(BaseModel):
    """
    专门用于处理 SubMessageType.SECURITY_REVIEW 的 content 字段结构。
    当 AI 安全审核通过或拒绝工具调用时产生，不阻断执行，仅供事后核查。
    """
    tool_call_id: str = Field(..., description="被审核的工具调用 ID")
    tool_name: str = Field(..., description="被审核的工具名称")
    risk_level: str = Field(..., description="AI 评估的风险等级: low / medium / high / critical")
    reason: str = Field(..., description="AI 审核理由")
    passed: bool = Field(..., description="True=审核通过自动放行, False=审核不通过升级人工")

    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'SecurityReviewContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for SecurityReviewContent: {e}")


class AskUserContent(BaseModel):
    """
    专门用于处理 SubMessageType.ASK_USER 的 content 字段结构。
    当 AI 调用 ask_user 工具时，中断产生的提问子消息。
    """
    tool_call_id: str = Field(..., description="ask_user 工具调用 ID")
    questions: List[Dict[str, Any]] = Field(..., description="问题列表")
    answers: Optional[List[str]] = Field(None, description="用户回答，None 表示尚未回答")
    interrupt_index: int = Field(..., description="中断事件中的序号")
    batch_id: str = Field(..., description="中断批次号")
    ask_status: Optional[str] = Field(None, description="回答状态: 'answered' / 'cancelled' / None(待回答)")
    interrupt_id: Optional[str] = Field(None, description="LangGraph 中断 ID，用于多中断恢复场景精确匹配")

    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'AskUserContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for AskUserContent: {e}")


class TaskSubStepContent(BaseModel):
    """TaskSubStep 子消息的 content JSON 结构。

    每条子代理内部消息（推理 / 正文 / 工具调用 / 工具结果）对应一个 SubMessage，
    content 字段存储此模型的 JSON。
    前端通过 display_type 决定渲染方式：
      - reasoning → 折叠式思考区
      - text       → Markdown 正文
      - tool_call  → 可点击工具调用按钮
      - tool_result → 工具结果文本
    """
    tool_call_id: str = Field(..., description="主代理 task 工具调用的 tool_call_id")
    subagent_type: str = Field(..., description="子代理类型名称，如 'general-purpose'")
    display_type: Literal["reasoning", "text", "tool_call", "tool_result"]
    content: str = ""
    tool_name: Optional[str] = Field(None, description="工具名（tool_call / tool_result 时）")
    tool_args: Optional[Dict[str, Any]] = Field(None, description="工具参数（tool_call 时）")
    step_order: int = Field(0, description="同组内的序号，前端排序用")
    description: Optional[str] = Field(None, description="task 描述（仅首条 step 携带）")
    sub_tool_call_id: Optional[str] = Field(None, description="子代理内部工具调用的 tool_call_id，用于绑定 AI 审核/中断审核事件")

    def to_json_string(self) -> str:
        """序列化为存储在 DB content 字段的 JSON 字符串"""
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_json_string(cls, json_str: str) -> 'TaskSubStepContent':
        """从 DB content 字符串反序列化"""
        if not json_str:
            raise ValueError("Empty content")
        try:
            data = json.loads(json_str)
            return cls(**data)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON for TaskSubStepContent: {e}")
