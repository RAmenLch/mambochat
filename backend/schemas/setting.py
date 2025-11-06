# backend/schemas/setting.py
from pydantic import BaseModel, Field
from typing import Optional


# --- Global Settings Schemas ---
class GlobalSetting(BaseModel):
    key: str
    value: Optional[str] = None


class GlobalSettingsUpdate(BaseModel):
    """用于更新全局配置的请求体"""
    default_model_id: Optional[str] = Field(None, description="全局默认模型的ID")
    title_generation_model_id: Optional[str] = Field(None, description="专门用于生成标题的模型ID, 未设置则使用全局默认模型")
    last_selected_provider_id: Optional[str] = Field(None, description="最后编辑或选择的服务商ID")
    # 新增的全局模型参数
    default_max_context_messages: Optional[int] = Field(None, description="默认上下文消息数量")
    default_temperature: Optional[float] = Field(None, description="默认Temperature")
    default_top_p: Optional[float] = Field(None, description="默认Top P")
    default_stream: Optional[bool] = Field(None, description="默认是否开启流式对话")
    # 新增的全局代理配置
    proxy_enabled: Optional[bool] = Field(None, description="是否全局启用代理")
    proxy_url: Optional[str] = Field(None, description="代理服务器的URL, 例如: http://127.0.0.1:7890")

