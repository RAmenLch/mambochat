# backend/schemas/provider.py
import json
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any

from backend.schemas.enums import ProviderWorkerType, ModelType


# --- AIModel Meta Config Schema ---

class AIModelMetaConfig(BaseModel):
    """存储模型的元配置信息"""
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    tokenizer: Optional[str] = None
    input_modalities: Optional[List[str]] = None
    output_modalities: Optional[List[str]] = None
    supported_parameters: Optional[List[str]] = None
    embedding_dimension: Optional[int] = Field(None, description="Embeddings 模型的输出向量维度")
    max_context_length: Optional[int] = Field(None, description="Embeddings 模型的最大上下文Token限制")
    max_retries: Optional[int] = Field(0, description="模型请求最大重试次数, 0表示不配置, 使用全局默认值")


# --- AIModel Schemas ---

class AIModelBase(BaseModel):
    modelId: str
    name: str
    meta_config: Optional[AIModelMetaConfig] = Field(None, description="模型的元配置信息")
    model_type: ModelType = Field(ModelType.CHAT, description="模型类型: chat 或 embedding")
    starred: bool = Field(False, description="是否标星")


class AIModelCreate(AIModelBase):
    providerId: str


class AIModelUpdate(BaseModel):
    """用于更新AI模型信息"""
    name: Optional[str] = None
    meta_config: Optional[AIModelMetaConfig] = None
    model_type: Optional[ModelType] = None
    starred: Optional[bool] = None


class AIModel(AIModelBase):
    id: str
    providerId: str

    @field_validator('meta_config', mode='before')
    @classmethod
    def parse_meta_config(cls, v: Any) -> Optional[dict]:
        """
        在验证之前，将从数据库取出的 JSON 字符串解析为字典，
        以确保 Pydantic 模型能够正确处理来自 ORM 的数据。
        """
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None  # 如果字符串不是有效的JSON，则视为None
        return v

    class Config:
        from_attributes = True


# --- AIProvider Schemas ---

class AIProviderBase(BaseModel):
    name: str
    apiHost: str
    worker_type: ProviderWorkerType = Field(ProviderWorkerType.OPENAI, description="后端使用的 Worker 类型")


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
    worker_type: Optional[ProviderWorkerType] = None


class AIProvider(AIProviderBase):
    id: str
    use_proxy: bool

    class Config:
        from_attributes = True


class AIProviderWithModels(AIProvider):
    # noinspection PyDataclass
    models: List[AIModel] = Field(default_factory=list)


class ProviderWithModelsCreate(AIProviderCreate):
    """用于在创建服务商时，同时创建其下的模型列表"""
    # noinspection PyDataclass
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
