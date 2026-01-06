# backend/schemas/resource.py

from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.schemas.message import SubMessageConfig
from backend.schemas.enums import MoveAction


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

    class Config:
        from_attributes = True


# --- Resource Schemas ---

class ResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    itemType: str = Field('resource', description="项目类型: 'resource' 或 'folder'")
    resourceType: Optional[str] = Field(None, description="资源类型, 例如 'system_prompt', 'submessage_template'")
    parentId: Optional[str] = None
    sortOrder: int = 0


class ResourceCreate(ResourceBase):
    initial_content: Optional[str] = Field(None, description="创建资源时，为其初始版本设置的内容")
    initial_attributes: Optional[Dict[str, Any]] = Field(None, description="创建资源时，为其初始版本设置的属性")

    @model_validator(mode='after')
    def check_template_attributes(self) -> 'ResourceCreate':
        if self.resourceType == 'submessage_template' and self.initial_attributes is not None:
            try:
                # 验证 'submessage_template' 类型的 attributes 字段是否符合 SubMessageConfig 规范
                SubMessageConfig.model_validate(self.initial_attributes)
            except Exception as e:
                raise ValueError(f"Attributes for submessage_template are invalid: {e}")
        return self


class ResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None


class ResourceSimple(ResourceBase):
    """
    轻量级资源模型，不包含 latest_version 信息。
    用于目录树懒加载等对性能要求较高的场景。
    """
    id: str
    createdAt: datetime
    updatedAt: datetime

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
