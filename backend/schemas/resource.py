# backend/schemas/resource.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


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
    resourceType: Optional[str] = Field(None, description="资源类型, 例如 'system_prompt'")
    parentId: Optional[str] = None
    sortOrder: int = 0


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None


class Resource(ResourceBase):
    id: str
    createdAt: datetime
    updatedAt: datetime
    latest_version: Optional[ResourceVersion] = None

    class Config:
        from_attributes = True


class ResourceWithVersions(Resource):
    # noinspection PyDataclass
    versions: List[ResourceVersion] = Field(default_factory=list)


class ResourceReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int

