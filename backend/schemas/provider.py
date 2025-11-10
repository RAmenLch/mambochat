# backend/schemas/provider.py
from pydantic import BaseModel, Field
from typing import Optional, List


# --- AIModel Meta Config Schema ---

class AIModelMetaConfig(BaseModel):
    """存储模型的元配置信息"""
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    tokenizer: Optional[str] = None
    input_modalities: Optional[List[str]] = None
    output_modalities: Optional[List[str]] = None
    supported_parameters: Optional[List[str]] = None


# --- AIModel Schemas ---

class AIModelBase(BaseModel):
    modelId: str
    name: str
    meta_config: Optional[AIModelMetaConfig] = Field(None, description="模型的元配置信息")


class AIModelCreate(AIModelBase):
    providerId: str


class AIModelUpdate(BaseModel):
    """用于更新AI模型信息"""
    name: Optional[str] = None
    meta_config: Optional[AIModelMetaConfig] = None


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
    use_proxy: bool = Field(False, description="是否为此服务商启用代理")


class AIProviderUpdate(BaseModel):
    """用于更新AI服务商信息"""
    name: Optional[str] = None
    apiHost: Optional[str] = None
    apiKey: Optional[str] = None
    use_proxy: Optional[bool] = None


class AIProvider(AIProviderBase):
    id: str
    use_proxy: bool

    class Config:
        from_attributes = True


class AIProviderWithModels(AIProvider):
    models: List[AIModel] = Field(default_factory=list)


class ProviderWithModelsCreate(AIProviderCreate):
    """用于在创建服务商时，同时创建其下的模型列表"""
    models: List[AIModelBase] = Field(default_factory=list, description="随服务商一同创建的模型列表")


# --- Connection Schemas ---

class ConnectionRequest(BaseModel):
    """用于测试连接或获取外部模型列表的请求体"""
    apiHost: str
    apiKey: str


class ConnectionTestForExistingProviderRequest(BaseModel):
    """为已存在的服务商测试连接的请求体，apiKey 由后端从数据库获取"""
    apiHost: str


class ConnectionTestResponse(BaseModel):
    """连接测试的响应体"""
    status: str
    message: str
