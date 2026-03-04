# backend/schemas/file.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class FileBase(BaseModel):
    """文件共享的基本字段"""
    filename: str
    mime_type: str
    size: int

class FileCreate(FileBase):
    """用于创建文件的Schema，支持预生成ID"""
    id: Optional[str] = None
    management_type: str

class FileUpdate(BaseModel):
    """用于更新文件内容的Schema"""
    content: str

class FileContentResponse(BaseModel):
    """用于返回文件文本内容的响应模型"""
    content: str

class File(FileBase):
    """用于API响应的文件模型"""
    id: str
    created_at: datetime
    url: str
    editable: bool

    class Config:
        from_attributes = True
