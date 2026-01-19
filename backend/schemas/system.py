# backend/schemas/system.py
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Any

from backend.schemas.enums import ProviderWorkerType

class LLMParameterDefinition(BaseModel):
    """
    定义一个LLM参数的结构，用于API响应，供前端UI生成和校验。
    """
    key: str = Field(..., description="唯一的参数标识符。")
    label: str = Field(..., description="在前端UI中展示的名称。")
    path: List[str] = Field(..., description="构建API请求体的路径。")
    description: str = Field(..., description="参数功能的详细描述。")
    type: str = Field(..., description="参数值的数据类型 (e.g., 'integer', 'number', 'string', 'boolean')。")
    limit: Optional[Union[List[Any], dict[str, float]]] = Field(None, description="值的约束，如枚举列表或min/max范围。")
    default_value: Any = Field(..., description="参数被启用时的默认值。")
    default_activate:bool = Field(...,description="参数是否默认显示/初始化")
    class Config:
        from_attributes = True


class DefaultProviderInfo(BaseModel):
    """
    定义预设服务商的基本信息，用于API响应。
    """
    name: str
    apiHost: str
    worker_type: ProviderWorkerType = Field(..., description="后端使用的 Worker 类型")


class SystemConfigResponse(BaseModel):
    """
    GET /api/system-config 接口的响应模型。
    """
    llm_parameters: List[LLMParameterDefinition] = Field(..., description="系统支持的所有LLM参数的定义列表。")
    default_providers: List[DefaultProviderInfo] = Field(..., description="用于快速创建的预设服务商列表。")
