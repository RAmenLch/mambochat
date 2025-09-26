# backend/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

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
    # --- 修正点 1 ---
    # 使用 Field(default_factory=list) 替代 = []
    models: List[AIModel] = Field(default_factory=list)


# --- Chat Schemas ---

class ChatBase(BaseModel):
    name: str
    systemPrompt: Optional[str] = None
    modelParameters: Optional[str] = None # 暂时作为字符串处理
    aiModelId: Optional[str] = None

class ChatCreate(ChatBase):
    pass

# 用于API响应的Chat模型，包含id和创建时间
class Chat(ChatBase):
    id: str
    createdAt: datetime

    class Config:
        from_attributes = True

# 用于获取单个Chat及其所有Message的完整信息
# noinspection PyDataclass
class ChatWithMessages(Chat):
    # --- 修正点 2 ---
    # 使用 Field(default_factory=list) 替代 = []
    messages: List[Message] = Field(default_factory=list)

class GenerateRequest(BaseModel):
    content: str