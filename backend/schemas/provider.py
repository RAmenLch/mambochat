# backend/schemas/provider.py
from pydantic import BaseModel, Field
from typing import Optional, List


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

# noinspection PyDataclass
class AIProviderWithModels(AIProvider):
    models: List[AIModel] = Field(default_factory=list)

# noinspection PyDataclass
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

