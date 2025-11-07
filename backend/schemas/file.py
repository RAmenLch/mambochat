# backend/schemas/file.py

from pydantic import BaseModel
from datetime import datetime

class FileBase(BaseModel):
    """文件共享的基本字段"""
    filename: str
    mime_type: str
    size: int

class File(FileBase):
    """用于API响应的文件模型"""
    id: str
    created_at: datetime
    url: str  # 文件的可访问URL，将在服务层动态生成

    class Config:
        from_attributes = True

