# backend/schemas/message.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
import json

from .enums import MessageRole, MessageStatus, SubMessageType
from .file import File as FileSchema  # 导入文件模型以供类型提示


# --- SubMessage Schemas ---

class SubMessageConfig(BaseModel):
    is_collapsed: bool = Field(False, description="分区是否折叠")
    context_participation_length: Optional[int] = Field(None,
                                                        description="参加上下文长度: None(默认)-参与; 0-不参与; N>0-在倒数N条内参与")


class SubMessageBase(BaseModel):
    content: str
    type: SubMessageType = Field(SubMessageType.NORMAL, description="分区类型，例如 Normal, Reasoning, File, Usage 等")
    config: SubMessageConfig = Field(default_factory=SubMessageConfig, description="分区的配置项")
    status: MessageStatus = Field(MessageStatus.COMPLETED, description="分区的状态")


class SubMessageCreate(SubMessageBase):
    sortOrder: int = Field(..., description="分区的排序权重")


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

