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

# --- 新增 1: 用于更新消息内容的模型 ---
class MessageUpdate(BaseModel):
    content: str

class Message(MessageBase):
    id: str
    createdAt: datetime
    chatId: str

    class Config:
        from_attributes = True # Pydantic v2, 替代 orm_mode

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
    # 创建时允许用户指定 id，如 'openai', 'google'
    id: Optional[str] = Field(None, description="自定义ID，如 'openai'，若不提供则自动生成UUID")
    apiKey: str

# 用于API响应，不应包含 apiKey
class AIProvider(AIProviderBase):
    id: str

    class Config:
        from_attributes = True

# 用于获取 Provider 及其下所有 Models 的完整信息
# noinspection PyDataclass
class AIProviderWithModels(AIProvider):
    models: List[AIModel] = Field(default_factory=list)


# --- Chat Schemas ---

class ChatBase(BaseModel):
    name: str
    systemPrompt: Optional[str] = None
    # 将 modelParameters 从字符串改为字典类型，以便进行结构化验证
    modelParameters: Optional[Dict] = Field(None, description="模型参数，例如 {'temperature': 0.7, 'top_p': 0.9}")
    aiModelId: Optional[str] = None

    # 这个验证器会在 Pydantic 进行标准验证之前运行 (mode='before')。
    # 它的作用是检查 modelParameters 字段：
    # 1. 如果它是一个字符串 (通常是从数据库的 TEXT 字段加载时的情况)，
    #    则尝试将其作为 JSON 解析成字典。
    # 2. 如果它已经是字典或None，则直接返回。
    # 这样就解决了 ORM 对象中的 str 类型与 Pydantic schema 的 dict 类型不匹配的问题。
    @field_validator("modelParameters", mode="before")
    @classmethod
    def parse_model_parameters(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # 如果数据库中的字符串不是有效的JSON，则返回None，避免程序崩溃
                return None
        return v

class ChatCreate(ChatBase):
    pass

# 用于API响应的Chat模型，包含id和创建时间
class Chat(ChatBase):
    id: str
    createdAt: datetime

    class Config:
        from_attributes = True

# 用于更新会话配置的 Schema
class ChatUpdate(BaseModel):
    """用于更新会话信息，所有字段均为可选"""
    name: Optional[str] = None
    aiModelId: Optional[str] = None
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = None

# 用于获取单个Chat及其所有Message的完整信息
# noinspection PyDataclass
class ChatWithMessages(Chat):
    messages: List[Message] = Field(default_factory=list)

class GenerateRequest(BaseModel):
    content: str

