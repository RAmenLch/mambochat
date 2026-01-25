# backend/models/resource_model.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func, Integer, JSON
from sqlalchemy.orm import relationship
from backend.models.base_model import Base, generate_uuid
from backend.schemas.enums import ResourceItemType


class Resource(Base):
    """
    模型，用于存储资源中心的目录项，可以是具体资源或文件夹。
    它不直接存储内容，而是通过 latestVersionId 指向当前活跃的版本。
    """
    __tablename__ = "Resource"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, index=True)
    description = Column(TEXT, nullable=True)
    createdAt = Column(DateTime, nullable=False, default=func.now())
    updatedAt = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # 使用枚举值作为默认值
    itemType = Column(String(20), nullable=False, default=ResourceItemType.RESOURCE.value, index=True)
    resourceType = Column(String(50), nullable=True, index=True)

    parentId = Column(String(36), ForeignKey("Resource.id"), nullable=True)
    sortOrder = Column(Integer, nullable=False, default=0)

    latestVersionId = Column(String(36), ForeignKey("ResourceVersion.id"), nullable=True)

    # 新增：指向所属知识库的 Resource ID
    kb_id = Column(String(36), nullable=True, index=True)

    # 新增：存储该资源的切分配置（Splitter Config），版本间共享
    kb_config = Column(JSON, nullable=True)

    versions = relationship(
        "ResourceVersion",
        back_populates="resource",
        cascade="all, delete-orphan",
        order_by="ResourceVersion.sortOrder.asc()",
        foreign_keys="[ResourceVersion.resourceId]"
    )

    # post_update=True 用于解决删除操作时的循环依赖
    latest_version = relationship(
        "ResourceVersion",
        foreign_keys=[latestVersionId],
        post_update=True
    )

    children = relationship("Resource", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Resource", remote_side=[id], back_populates="children")


class ResourceVersion(Base):
    """
    模型，用于存储一个资源的具体内容快照（版本）。
    每个版本都是一个独立、可编辑的状态。
    """
    __tablename__ = "ResourceVersion"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    resourceId = Column(String(36), ForeignKey("Resource.id"), nullable=False, index=True)

    name = Column(String(100), nullable=False, default="默认版本")
    sortOrder = Column(Integer, nullable=False, default=0)
    commitMessage = Column(String(255), nullable=True)
    createdAt = Column(DateTime, nullable=False, default=func.now())
    updatedAt = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    content = Column(TEXT, nullable=True)
    attributes = Column(JSON, nullable=True)

    resource = relationship(
        "Resource",
        back_populates="versions",
        foreign_keys=[resourceId]
    )
