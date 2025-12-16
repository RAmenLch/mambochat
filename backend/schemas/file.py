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
    """[新增] 用于创建文件的Schema，支持预生成ID"""
    id: Optional[str] = None
    management_type: str

class File(FileBase):
    """用于API响应的文件模型"""
    id: str
    created_at: datetime
    url: str

    class Config:
        from_attributes = True
