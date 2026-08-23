"""MamboChat 会话导出（mambochat.chat-export）格式模型。

对应 doc/chat-export-spec.md。
所有模型以 extra='ignore' 解析未知字段，保证向前兼容（规范 §8）。
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExportFileRef(BaseModel):
    """File 类型子消息的文件元信息 + blob 引用"""
    model_config = ConfigDict(extra='ignore')

    filename: str
    mimeType: str
    size: int
    blobId: str


class ExportSubMessage(BaseModel):
    """messages[].subMessages[] 中的子消息"""
    model_config = ConfigDict(extra='ignore')

    type: str
    content: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: str
    sortOrder: int
    createdAt: datetime
    file: Optional[ExportFileRef] = None  # 仅 File 类型携带


class ExportMessage(BaseModel):
    """messages[] 中的消息（活跃线性路径，有序）"""
    model_config = ConfigDict(extra='ignore')

    role: str
    createdAt: datetime
    subMessages: List[ExportSubMessage] = Field(default_factory=list)


class ExportChat(BaseModel):
    """chat 段：会话本体"""
    model_config = ConfigDict(extra='ignore')

    name: str
    createdAt: datetime
    chatMode: str = "normal"
    systemPrompt: Optional[str] = None


class ExportBlob(BaseModel):
    """blobs[] 载荷段"""
    model_config = ConfigDict(extra='ignore')

    blobId: str
    filename: str
    mimeType: str
    size: int
    encoding: Literal["base64"] = "base64"
    data: str


class ChatExportPackage(BaseModel):
    """顶层包结构（规范 §3）"""
    model_config = ConfigDict(extra='ignore')

    format: str
    formatVersion: str
    mambochatVersion: str
    exportedAt: datetime
    chat: ExportChat
    messages: List[ExportMessage] = Field(default_factory=list)
    blobs: List[ExportBlob] = Field(default_factory=list)


class ImportReport(BaseModel):
    """导入报告（规范 §7.1 步 6）"""
    chat_id: str
    name: str
    message_count: int
    file_count: int
