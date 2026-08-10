# backend/schemas/resource_completion.py

from pydantic import BaseModel, Field
from typing import List, Optional


class ResourceCompletePathRequest(BaseModel):
    """路径补全请求：按 agent 挂载的 ResourceBackend 子树检索。"""
    agent_id: str = Field(..., description="当前会话绑定的 Agent ID")
    prefix: str = Field("", description="已输入的路径前缀，如 'foo/bar' 或 'foo/'")
    limit: int = Field(50, ge=1, le=200, description="最大候选数量")


class ResourceCompletePathItem(BaseModel):
    """路径补全候选：挂载子树内的一个直接子节点。"""
    name: str = Field(..., description="节点名称")
    item_type: str = Field(..., description="'resource' 或 'folder'")
    resource_type: Optional[str] = Field(None, description="资源业务类型")
    path: str = Field("", description="节点所在目录路径（不包含自身）")
    is_dir: bool = Field(..., description="是否为文件夹")


class ResourceCompletePathResponse(BaseModel):
    enabled: bool = Field(..., description="当前 Agent 是否挂载了 ResourceBackend")
    items: List[ResourceCompletePathItem] = Field(default_factory=list)


class ResourceContentCompleteRequest(BaseModel):
    """内容续写请求：在挂载子树内检索资源内容中前缀之后的续写片段。"""
    agent_id: str = Field(..., description="当前会话绑定的 Agent ID")
    prefix: str = Field(..., min_length=1, description="内容前缀，如 'const x = '")
    limit: int = Field(120, ge=1, le=500, description="续写片段软上限字符数（优先按边界符号截断，不含符号本身）")
    max_items: int = Field(20, ge=1, le=50, description="最大候选数量")


class ResourceContentCompleteItem(BaseModel):
    """内容续写候选。"""
    resource_id: str = Field(..., description="命中的资源 ID")
    resource_path: str = Field("", description="资源所在目录路径")
    snippet: str = Field("", description="前缀之后的续写片段")


class ResourceContentCompleteResponse(BaseModel):
    enabled: bool = Field(..., description="当前 Agent 是否挂载了 ResourceBackend")
    items: List[ResourceContentCompleteItem] = Field(default_factory=list)
