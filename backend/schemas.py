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


class MessageStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Message Schemas ---

class MessageBase(BaseModel):
    content: str
    role: MessageRole


class MessageCreate(MessageBase):
    status: Optional[MessageStatus] = MessageStatus.COMPLETED


class MessageUpdate(BaseModel):
    """用于更新消息内容，可选择是否重新触发生成"""
    content: str
    resend: Optional[bool] = Field(False, description="仅对用户消息有效。若为true，更新内容后将删除此消息之后的所有对话并重新生成AI回答。")


class Message(MessageBase):
    id: str
    createdAt: datetime
    chatId: str
    sortOrder: int
    status: MessageStatus

    class Config:
        from_attributes = True


# --- AIModel Schemas ---

class AIModelBase(BaseModel):
    modelId: str
    name: str


class AIModelCreate(AIModelBase):
    providerId: str


class AIModelUpdate(BaseModel):
    """用于更新AI模型信息"""
    name: Optional[str] = None


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


class AIProviderUpdate(BaseModel):
    """用于更新AI服务商信息"""
    name: Optional[str] = None
    apiHost: Optional[str] = None
    apiKey: Optional[str] = None


class AIProvider(AIProviderBase):
    id: str

    class Config:
        from_attributes = True


class AIProviderWithModels(AIProvider):
    models: List[AIModel] = Field(default_factory=list)


class ProviderWithModelsCreate(AIProviderCreate):
    """用于在创建服务商时，同时创建其下的模型列表"""
    models: List[AIModelBase] = Field(default_factory=list, description="随服务商一同创建的模型列表")


class ConnectionRequest(BaseModel):
    """用于测试连接或获取外部模型列表的请求体"""
    apiHost: str
    apiKey: str


class ConnectionTestResponse(BaseModel):
    """连接测试的响应体"""
    status: str
    message: str


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


class ChatWithMessages(Chat):
    messages: List[Message] = Field(default_factory=list)


class ChatReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int


class GenerateRequest(BaseModel):
    content: str


# --- Global Settings Schemas ---
class GlobalSetting(BaseModel):
    key: str
    value: Optional[str] = None


class GlobalSettingsUpdate(BaseModel):
    """用于更新全局配置的请求体"""
    default_model_id: Optional[str] = Field(None, description="全局默认模型的ID")
    last_selected_provider_id: Optional[str] = Field(None, description="最后编辑或选择的服务商ID")
    # 新增的全局模型参数
    default_max_context_messages: Optional[int] = Field(None, description="默认上下文消息数量")
    default_temperature: Optional[float] = Field(None, description="默认Temperature")
    default_top_p: Optional[float] = Field(None, description="默认Top P")
    default_stream: Optional[bool] = Field(None, description="默认是否开启流式对话")

