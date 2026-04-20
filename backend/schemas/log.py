# backend/schemas/log.py

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any


class PostLogResponse(BaseModel):
    """用于 API 响应的 MamboPostLog Schema"""
    id: str
    createdAt: datetime

    chatId: Optional[str] = None
    messageId: Optional[str] = None

    managerName: Optional[str] = None
    agentName: Optional[str] = None

    configMetaData: Optional[Dict[str, Any]] = None
    rawPayload: Optional[Dict[str, Any]] = None

    # Pydantic V2 配置，允许从 ORM 模型直接转换
    model_config = ConfigDict(from_attributes=True)


class PaginatedPostLogResponse(BaseModel):
    """分页的 MamboPostLog 响应 Schema"""
    total: int = Field(..., description="满足条件的总记录数")
    items: List[PostLogResponse] = Field(default_factory=list, description="当前页的日志记录列表")

