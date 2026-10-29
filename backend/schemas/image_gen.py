# backend/schemas/image_gen.py

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field

from backend.services.generation.agent.image_gen.standard import (
    DEFAULT_COUNT,
    MAX_COUNT,
)


class ImageGenConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    description: Optional[str] = Field(None, description="说明")
    mcpServerId: str = Field(..., description="绑定的 MCP 服务 ID")
    defaultCount: int = Field(DEFAULT_COUNT, ge=1, le=MAX_COUNT, description="默认生成数量")
    defaultSync: bool = Field(True, description="默认是否同步等待生成完成")
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
    timeout: Optional[float] = None
    isEnabled: Optional[bool] = None


class ImageGenConfigResponse(ImageGenConfigBase):
    id: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


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
