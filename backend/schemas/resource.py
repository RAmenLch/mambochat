# backend/schemas/resource.py

from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.schemas.message import SubMessageConfig
from backend.schemas.enums import MoveAction, ResourceItemType, ResourceType
from backend.schemas.file import File as FileSchema  # 导入 File Schema


# --- ResourceVersion Schemas ---

class ResourceVersionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    commitMessage: Optional[str] = None
    content: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class ResourceVersionCreate(ResourceVersionBase):
    pass


class ResourceVersionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    commitMessage: Optional[str] = None
    content: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class ResourceVersion(ResourceVersionBase):
    id: str
    resourceId: str
    sortOrder: int
    createdAt: datetime
    updatedAt: datetime

    # [新增] 用于返回文件详细信息，不存数据库
    file_info: Optional[FileSchema] = None

    class Config:
        from_attributes = True


# --- Resource Schemas ---

class ResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None

    itemType: ResourceItemType = Field(ResourceItemType.RESOURCE, description="项目类型: 'resource' 或 'folder'")

    resourceType: Optional[ResourceType] = Field(None,
                                                 description="资源类型, 例如 'system_prompt', 'submessage_template', 'file'")

    parentId: Optional[str] = None
    sortOrder: int = 0

    kb_id: Optional[str] = Field(None, description="关联的知识库ID")
    kb_config: Optional[Dict[str, Any]] = Field(None, description="切分配置")


class ResourceCreate(ResourceBase):
    initial_content: Optional[str] = Field(None, description="创建资源时，为其初始版本设置的内容")
    initial_attributes: Optional[Dict[str, Any]] = Field(None, description="创建资源时，为其初始版本设置的属性")

    @model_validator(mode='after')
    def check_template_attributes(self) -> 'ResourceCreate':
        if self.resourceType == ResourceType.SUBMESSAGE_TEMPLATE and self.initial_attributes is not None:
            try:
                SubMessageConfig.model_validate(self.initial_attributes)
            except Exception as e:
                raise ValueError(f"Attributes for submessage_template are invalid: {e}")
        return self


class ResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None
    kb_id: Optional[str] = None
    kb_config: Optional[Dict[str, Any]] = None


class ResourceSimple(ResourceBase):
    """
    轻量级资源模型，不包含 latest_version 信息。
    """
    id: str
    createdAt: datetime
    updatedAt: datetime

    kb_id: Optional[str] = None
    kb_config: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class Resource(ResourceSimple):
    """
    完整资源模型，包含 latest_version 信息。
    """
    latest_version: Optional[ResourceVersion] = None


class ResourceWithVersions(Resource):
    # noinspection PyDataclass
    versions: List[ResourceVersion] = Field(default_factory=list)


class ResourceReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int


class ResourceMoveRequest(BaseModel):
    item_ids: List[str] = Field(..., description="被移动的资源或文件夹ID列表")
    reference_id: str = Field(..., description="参考目标ID，'root'代表根目录")
    action: MoveAction = Field(..., description="移动行为: before, after, inside")


class ResourceSearchRequest(BaseModel):
    keyword: str = Field(..., description="搜索关键词或正则模式")
    root_id: Optional[str] = Field(None, description="搜索范围的根目录ID，不传则搜索全局")
    enable_regex: bool = Field(False, description="是否启用正则匹配")
    page_num: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class ResourceSearchResultItem(BaseModel):
    resource_id: str
    resource_name: str
    resource_path: str
    match_type: str = Field(..., description="匹配类型: 'content', 'name', 'description'")
    context_text: str = Field(..., description="包含关键词的高亮上下文片段")
    version_id: Optional[str] = Field(None, description="如果是内容匹配，提供对应的版本ID")
    updated_at: datetime


class ResourceSearchResponse(BaseModel):
    total: int
    items: List[ResourceSearchResultItem]
