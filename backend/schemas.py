# backend/schemas.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
import json


# --- 枚举类型 ---

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# --- Message Schemas ---

class MessageBase(BaseModel):
    content: str
    role: MessageRole


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str


class Message(MessageBase):
    id: str
    createdAt: datetime
    chatId: str

    class Config:
        from_attributes = True


# --- AIModel Schemas ---

class AIModelBase(BaseModel):
    modelId: str
    name: str


class AIModelCreate(AIModelBase):
    providerId: str


class AIModel(AIModelBase):
    id: str
    providerId: str

    class Config:
        from_attributes = True


# --- AIProvider Schemas ---

class AIProviderBase(BaseModel):
    name: str
    apiHost: str


class AIProviderCreate(AIProviderBase):
    id: Optional[str] = Field(None, description="自定义ID，如 'openai'，若不提供则自动生成UUID")
    apiKey: str


class AIProvider(AIProviderBase):
    id: str

    class Config:
        from_attributes = True

# noinspection PyDataclass
class AIProviderWithModels(AIProvider):
    models: List[AIModel] = Field(default_factory=list)


# --- Chat Schemas ---

class ChatBase(BaseModel):
    name: str
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = Field(None, description="模型参数，例如 {'temperature': 0.7, 'top_p': 0.9}")
    aiModelId: Optional[str] = None

    # --- 新增字段，用于支持文件夹和排序 ---
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
    # --- 新增字段，用于支持最近会话功能 ---
    lastOpenedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatUpdate(BaseModel):
    """用于更新会话信息，所有字段均为可选"""
    name: Optional[str] = None
    aiModelId: Optional[str] = None
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = None
    # --- 新增字段，用于支持移动和重命名文件夹 ---
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None

# noinspection PyDataclass
class ChatWithMessages(Chat):
    messages: List[Message] = Field(default_factory=list)


# --- 新增Schema: 用于批量更新排序和层级关系 ---
class ChatReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int


class GenerateRequest(BaseModel):
    content: str
