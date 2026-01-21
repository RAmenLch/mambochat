# backend/schemas/kb.py

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class KBChunkStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# --- Chunk Models ---

class KBChunkBase(BaseModel):
    content: str
    chunk_index: int
    byte_size: int
    status: KBChunkStatus = KBChunkStatus.PENDING
    vector_id: Optional[int] = None


class KBChunkCreate(KBChunkBase):
    resource_id: str


class KBChunk(KBChunkBase):
    id: str
    resource_id: str

    class Config:
        from_attributes = True


# --- Search Models ---

class KBSearchRequest(BaseModel):
    query_text: str = Field(..., min_length=1, description="查询文本")
    kb_id: Optional[str] = Field(None, description="限定搜索的知识库ID (Resource ID)，若为空则搜索所有知识库")
    top_k: int = Field(5, ge=1, le=20, description="返回的最相似结果数量")


class KBSearchResultItem(BaseModel):
    chunk_id: str
    chunk_content: str
    score: float = Field(..., description="相似度分数 (距离越小越相似)")
    resource_id: str = Field(..., description="所属文件ID")
    resource_name: str = Field(..., description="所属文件名")
    kb_id: str = Field(..., description="所属知识库ID")
    kb_name: str = Field(..., description="所属知识库名称")


class KBSearchResponse(BaseModel):
    total: int
    items: List[KBSearchResultItem]


# --- Status & Ingestion Models ---

class KBProcessingStatus(BaseModel):
    """文件处理状态统计"""
    resource_id: str
    total_chunks: int
    pending_chunks: int
    completed_chunks: int
    failed_chunks: int
    # 聚合状态: PROCESSING (pending > 0), INDEXED (all completed), FAILED (failed > 0)
    file_status: str

class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = None
    parent_id: Optional[str] = Field(None, description="父文件夹ID")
    embedding_model_id: str = Field(..., description="使用的 Embedding 模型ID")