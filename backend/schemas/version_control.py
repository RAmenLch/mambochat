"""版本控制 API 响应 Schema"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VersionSnapshotResponse(BaseModel):
    """单个快照的 API 响应"""
    checkpoint_id: str = Field(..., description="Checkpoint ID")
    timestamp: str = Field(default="", description="快照创建时间（ISO-8601）")
    file_count: int = Field(default=0, description="该快照中变更的文件数量")
    changed_files: list[str] = Field(default_factory=list, description="变更的文件路径列表")


class VersionHistoryResponse(BaseModel):
    """会话的版本历史 API 响应"""
    thread_id: str = Field(..., description="会话/Thread ID")
    snapshots: list[VersionSnapshotResponse] = Field(default_factory=list, description="快照列表（按时间排序）")


class VersionFileContentResponse(BaseModel):
    """文件版本内容 API 响应"""
    path: str = Field(..., description="文件虚拟路径")
    checkpoint_id: str = Field(..., description="所属 checkpoint ID")
    content: Optional[str] = Field(None, description="文件内容（None 表示文件在该版本不存在）")
    sha256: Optional[str] = Field(None, description="内容 SHA256 哈希")


class DiffResponse(BaseModel):
    """文件差异对比响应"""
    path: str = Field(..., description="文件虚拟路径")
    checkpoint_id: str = Field(..., description="对比的目标 checkpoint ID")
    old_content: Optional[str] = Field(None, description="快照中的文件内容")
    current_content: Optional[str] = Field(None, description="当前文件内容")
    diff: str = Field(default="", description="unified diff 文本")
    read_error: Optional[str] = Field(None, description="读取当前文件时的错误信息（调试用）")
