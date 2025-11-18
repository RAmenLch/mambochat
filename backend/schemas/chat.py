# backend/schemas/chat.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict
import json

from .message import Message, SubMessageCreate


# --- Chat Schemas ---

class ChatBase(BaseModel):
    name: str
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = Field(None, description="模型参数，例如 {'temperature': 0.7, 'top_p': 0.9}")
    aiModelId: Optional[str] = None

    itemType: str = Field('chat', description="项目类型: 'chat' 或 'folder'")
    parentId: Optional[str] = Field(None, description="父文件夹的ID")
    sortOrder: int = Field(0, description="排序权重")

    @field_validator("modelParameters", mode="before")
    @classmethod
    def parse_model_parameters(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v


class ChatCreate(ChatBase):
    pass


class Chat(ChatBase):
    id: str
    createdAt: datetime
    lastOpenedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatUpdate(BaseModel):
    """用于更新会话信息，所有字段均为可选"""
    name: Optional[str] = None
    aiModelId: Optional[str] = None
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None


# noinspection PyDataclass
class ChatWithMessages(Chat):
    messages: List[Message] = Field(default_factory=list)


class ChatReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int


class GenerateRequest(BaseModel):
    sub_messages: List[SubMessageCreate]
    attachedSubmessageResourceIds: Optional[List[str]] = Field(None, description="本次发送时要附加的Submessage模板资源ID列表")


class PrepareGenerateResponse(BaseModel):
    """
    用于 /prepare-generate 端点的响应模型。
    """
    user_message: Message = Field(..., description="新创建的用户消息对象。")
    assistant_message: Message = Field(..., description="为AI回复创建的占位符消息对象。")

