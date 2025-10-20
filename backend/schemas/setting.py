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
    last_selected_provider_id: Optional[str] = Field(None, description="最后编辑或选择的服务商ID")
    # 新增的全局模型参数
    default_max_context_messages: Optional[int] = Field(None, description="默认上下文消息数量")
    default_temperature: Optional[float] = Field(None, description="默认Temperature")
    default_top_p: Optional[float] = Field(None, description="默认Top P")
    default_stream: Optional[bool] = Field(None, description="默认是否开启流式对话")

