# backend/routers/system_config.py

from fastapi import APIRouter

from ..schemas.system import SystemConfigResponse, LLMParameterDefinition, DefaultProviderInfo
from ..config.llm_parameters import SUPPORTED_LLM_PARAMETERS, DEFAULT_PROVIDERS

router = APIRouter()


@router.get(
    "/system-config",
    response_model=SystemConfigResponse,
    summary="获取系统级配置"
)
async def get_system_configuration():
    """
    提供前端UI所需的系统级配置信息，包括：
    - 所有系统支持的LLM参数的详细定义。
    - 用于快速创建服务商的预设模板列表。
    """
    # 将配置对象转换为API响应模型
    llm_parameter_definitions = [
        LLMParameterDefinition.model_validate(param) for param in SUPPORTED_LLM_PARAMETERS
    ]

    default_provider_info = [
        DefaultProviderInfo(**provider) for provider in DEFAULT_PROVIDERS
    ]

    return SystemConfigResponse(
        llm_parameters=llm_parameter_definitions,
        default_providers=default_provider_info
    )

