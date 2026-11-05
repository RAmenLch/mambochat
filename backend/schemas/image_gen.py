# backend/schemas/image_gen.py

from typing import Any, List, Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.services.generation.agent.image_gen.standard import (
    DEFAULT_COUNT,
    DEFAULT_RESOLUTION,
    MAX_COUNT,
    MAX_WAIT_TIMEOUT,
    parse_resolution,
)


def _validate_resolution(value: Optional[str]) -> str:
    """分辨率必须能解析为 ``宽x高``，否则回落默认值（服务侧同样会忽略非法值）。"""
    if not value:
        return DEFAULT_RESOLUTION
    size = parse_resolution(value)
    if size is None:
        return DEFAULT_RESOLUTION
    return f"{size[0]}x{size[1]}"


def _ensure_backend_binding(payload: Any) -> None:
    """``backendType`` 与绑定目标必须匹配：mcp 要服务，model 要模型。"""
    backend_type = (getattr(payload, "backendType", None) or "mcp").strip().lower()
    if backend_type == "model":
        if not (getattr(payload, "aiModelId", None) or "").strip():
            raise ValueError("后端类型为「系统模型」时必须绑定一个模型（aiModelId）")
    elif not (getattr(payload, "mcpServerId", None) or "").strip():
        raise ValueError("后端类型为「MCP 服务」时必须绑定一个 MCP 服务（mcpServerId）")


class ImageGenConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    description: Optional[str] = Field(None, description="说明")
    backendType: Literal["mcp", "model"] = Field(
        "mcp",
        description=(
            "后端类型：mcp（实现生图标准的 MCP 服务）/ model（系统里能出图的 Chat 模型）"
        ),
    )
    mcpServerId: Optional[str] = Field(
        None, description="绑定的 MCP 服务 ID（backendType=mcp 时必填）"
    )
    aiModelId: Optional[str] = Field(
        None, description="绑定的系统模型 ID（backendType=model 时必填）"
    )
    supportsReferenceImages: Optional[bool] = Field(
        None,
        description=(
            "是否支持参考图；null 表示自动探测（MCP 查服务 schema，模型后端恒为支持）"
        ),
    )
    defaultCount: int = Field(DEFAULT_COUNT, ge=1, le=MAX_COUNT, description="默认生成数量")
    defaultSync: bool = Field(True, description="默认是否同步等待生成完成")
    defaultResolution: str = Field(
        DEFAULT_RESOLUTION,
        description="默认分辨率（resolution），形如 1024x1024",
    )
    defaultWaitTimeout: int = Field(
        0,
        ge=0,
        le=MAX_WAIT_TIMEOUT,
        description="状态工具默认阻塞等待秒数（wait_timeout），0 表示不等待",
    )
    timeout: Optional[float] = Field(None, description="单次工具调用超时（秒）")
    enableStandardTools: bool = Field(
        True,
        description=(
            "是否启用契约三件套（image_generate / image_task_status / image_download）"
        ),
    )
    enableGenerateShow: bool = Field(
        False,
        description=(
            "是否启用一条龙工具 image_generate_show（生成 + 落盘 + 展示）"
        ),
    )
    isEnabled: bool = Field(True, description="是否启用")


class ImageGenConfigCreate(ImageGenConfigBase):
    @model_validator(mode="after")
    def _ensure_tool_mode(self) -> "ImageGenConfigCreate":
        if not self.enableStandardTools and not self.enableGenerateShow:
            raise ValueError("标准三件套与一条龙工具至少需要启用一个")
        _ensure_backend_binding(self)
        return self


class ImageGenConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    backendType: Optional[Literal["mcp", "model"]] = None
    mcpServerId: Optional[str] = None
    aiModelId: Optional[str] = None
    supportsReferenceImages: Optional[bool] = None
    defaultCount: Optional[int] = Field(None, ge=1, le=MAX_COUNT)
    defaultSync: Optional[bool] = None
    defaultResolution: Optional[str] = None
    defaultWaitTimeout: Optional[int] = Field(None, ge=0, le=MAX_WAIT_TIMEOUT)
    timeout: Optional[float] = None
    enableStandardTools: Optional[bool] = None
    enableGenerateShow: Optional[bool] = None
    isEnabled: Optional[bool] = None

    @model_validator(mode="after")
    def _ensure_not_both_off(self) -> "ImageGenConfigUpdate":
        if self.enableStandardTools is False and self.enableGenerateShow is False:
            raise ValueError("标准三件套与一条龙工具至少需要启用一个")
        return self


class ImageGenConfigResponse(ImageGenConfigBase):
    id: str
    defaultResolution: str = Field(DEFAULT_RESOLUTION)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_validator("defaultResolution", mode="before")
    @classmethod
    def _normalize_resolution(cls, value: Optional[str]) -> str:
        return _validate_resolution(value)


class ImageGenToolCheckResult(BaseModel):
    """生图标准合规检测结果。"""

    status: str = Field(..., description="healthy / unhealthy")
    server_name: Optional[str] = None
    backend_type: Optional[str] = None
    found_tools: List[str] = Field(default_factory=list)
    missing_tools: List[str] = Field(default_factory=list)
    supports_reference_images: Optional[bool] = Field(
        None, description="后端是否支持参考图（reference_images）"
    )
    message: str = ""
    error: Optional[str] = None


__all__ = [
    "ImageGenConfigBase",
    "ImageGenConfigCreate",
    "ImageGenConfigUpdate",
    "ImageGenConfigResponse",
    "ImageGenToolCheckResult",
]
