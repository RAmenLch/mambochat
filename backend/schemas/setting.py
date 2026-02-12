# backend/schemas/setting.py
from pydantic import BaseModel, Field
from typing import Optional


# --- Global Settings Schemas ---
class GlobalSetting(BaseModel):
    key: str
    value: Optional[str] = None


class GlobalSettingsUpdate(BaseModel):
    """用于更新和响应全局配置的模型"""
    default_model_id: Optional[str] = Field(None, description="全局默认模型的ID")
    title_generation_model_id: Optional[str] = Field(None, description="专门用于生成标题的模型ID, 未设置则使用全局默认模型")
    zip_history_system_prompt: Optional[str] = Field(None, description="用于对话历史压缩的System Prompt")
    last_selected_provider_id: Optional[str] = Field(None, description="最后编辑或选择的服务商ID")
    # 全局模型参数
    default_max_context_messages: Optional[int] = Field(None, description="默认上下文消息数量")
    default_temperature: Optional[float] = Field(None, description="默认Temperature")
    default_top_p: Optional[float] = Field(None, description="默认Top P")
    default_stream: Optional[bool] = Field(None, description="默认是否开启流式对话")
    default_enable_suggest: Optional[bool] = Field(None, description="默认是否开启回复建议生成")
    # 全局代理配置
    proxy_enabled: Optional[bool] = Field(None, description="是否全局启用代理")
    proxy_url: Optional[str] = Field(None, description="代理服务器的URL, 例如: http://127.0.0.1:7890")
    # 全局头像配置 (仅用于API响应)
    user_avatar_url: Optional[str] = Field(None, description="当前用户头像的访问URL")
    ai_avatar_url: Optional[str] = Field(None, description="当前AI助手头像的访问URL")

    # 前端与知识库默认配置
    frontend_editor: Optional[str] = Field("simple", description="前端编辑器类型: simple 或 monaco")
    kb_default_chunk_size: Optional[int] = Field(500, description="知识库默认切片大小")
    kb_default_chunk_overlap: Optional[int] = Field(50, description="知识库默认切片重叠大小")
    send_message_shortcut: Optional[str] = Field("enter", description="发送消息快捷键: enter 或 ctrl_enter")

    language: Optional[str] = Field("zh-CN", description="系统界面语言: zh-CN (简体中文) 或 en (英文)")
