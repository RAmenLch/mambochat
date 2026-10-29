# backend/schemas/image_gen.py

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

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


class ImageGenConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    description: Optional[str] = Field(None, description="说明")
    mcpServerId: str = Field(..., description="绑定的 MCP 服务 ID")
    defaultCount: int = Field(DEFAULT_COUNT, ge=1, le=MAX_COUNT, description="默认生成数量")
    defaultSync: bool = Field(True, description="默认是否同步等待生成完成")
    defaultResolution: str = Field(
        DEFAULT_RESOLUTION,
        description="默认分辨率（NumxNum），形如 1024x1024",
    )
    defaultWaitTimeout: int = Field(
        0,
        ge=0,
        le=MAX_WAIT_TIMEOUT,
        description="状态工具默认阻塞等待秒数（wait_timeout），0 表示不等待",
    )
    timeout: Optional[float] = Field(None, description="单次工具调用超时（秒）")
    isEnabled: bool = Field(True, description="是否启用")


class ImageGenConfigCreate(ImageGenConfigBase):
    pass


class ImageGenConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    mcpServerId: Optional[str] = None
    defaultCount: Optional[int] = Field(None, ge=1, le=MAX_COUNT)
    defaultSync: Optional[bool] = None
    defaultResolution: Optional[str] = None
    defaultWaitTimeout: Optional[int] = Field(None, ge=0, le=MAX_WAIT_TIMEOUT)
    timeout: Optional[float] = None
    isEnabled: Optional[bool] = None


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
    found_tools: List[str] = Field(default_factory=list)
    missing_tools: List[str] = Field(default_factory=list)
    message: str = ""
    error: Optional[str] = None


__all__ = [
    "ImageGenConfigBase",
    "ImageGenConfigCreate",
    "ImageGenConfigUpdate",
    "ImageGenConfigResponse",
    "ImageGenToolCheckResult",
]
