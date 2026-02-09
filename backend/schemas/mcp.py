# backend/schemas/mcp.py

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from datetime import datetime
from backend.schemas.enums import McpTransportType

class McpServerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    transportType: McpTransportType
    isEnabled: bool = True

    # Stdio 配置
    command: Optional[str] = None
    args: Optional[List[str]] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = Field(default_factory=dict)

    # SSE 配置
    url: Optional[str] = None

    @field_validator('url')
    def validate_url_if_sse(cls, v, values):
        if values.data.get('transportType') == McpTransportType.SSE:
            if not v:
                raise ValueError('URL is required for SSE transport')
            # 清理 URL 中的空白字符
            return v.strip()
        return v

    @field_validator('command')
    def validate_command_if_stdio(cls, v, values):
        if values.data.get('transportType') == McpTransportType.STDIO:
            if not v:
                raise ValueError('Command is required for stdio transport')
            # 清理命令中的空白字符
            return v.strip()
        return v

class McpServerCreate(McpServerBase):
    pass

class McpServerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    transportType: Optional[McpTransportType] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    isEnabled: Optional[bool] = None

class McpServerResponse(McpServerBase):
    id: str
    isSystem: bool = False  # 标记是否为系统内置工具

    # 状态监控字段
    last_status: Optional[str] = None
    last_test_at: Optional[datetime] = None
    last_error: Optional[str] = None

    class Config:
        from_attributes = True
