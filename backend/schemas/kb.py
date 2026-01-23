# backend/schemas/kb.py

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

from backend.schemas.enums import KBFileStatus


class KBChunkStatus(str, Enum):
    """定义单个切片在数据库中的状态"""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class KBSplitterType(str, Enum):
    SIMPLE = "simple"
    SEPARATOR = "separator"


class KBTaskAction(str, Enum):
    START = "start"   # 覆盖更新/重新切分
    RESUME = "resume" # 断点续连
    STOP = "stop"     # 停止任务


# --- Config Models ---

class KBTextSplitterConfig(BaseModel):
    splitter_type: KBSplitterType = Field(KBSplitterType.SIMPLE, description="切分器类型")
    chunk_size: int = Field(500, ge=50, le=5000, description="切片大小 (字符数)")
    chunk_overlap: int = Field(50, ge=0, description="切片重叠大小 (字符数)")
    separator: Optional[str] = Field(None, description="分隔符，仅当 splitter_type 为 separator 时有效，例如 '\\n\\n'")


class KBUpdateConfigRequest(BaseModel):
    splitter_config: KBTextSplitterConfig = Field(..., description="切分配置参数")


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


# --- Status & Task Models ---

class KBProcessingStatus(BaseModel):
    """文件处理状态统计 (快照)"""
    resource_id: str
    total_chunks: int
    pending_chunks: int
    completed_chunks: int
    failed_chunks: int
    stopped_chunks: int
    # 聚合状态，使用统一枚举
    file_status: KBFileStatus


class KBStreamEvent(BaseModel):
    """SSE 流式事件数据结构"""
    status: KBFileStatus
    message: str
    processed: int = 0
    total: int = 0


class KBRunTaskRequest(BaseModel):
    action: KBTaskAction = Field(..., description="任务动作: start(覆盖), resume(续连), stop(停止)")


class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = None
    parent_id: Optional[str] = Field(None, description="父文件夹ID")
    embedding_model_id: str = Field(..., description="使用的 Embedding 模型ID")
    embedding_rate_limit: float = Field(0.0, ge=0.0, description="嵌入请求频率限制(秒)，即每次请求后的等待时间")
