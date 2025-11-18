# backend/models/resource_model.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func, Integer, JSON
from sqlalchemy.orm import relationship
from .base_model import Base, generate_uuid


class ResourceVersionFileAssociation(Base):
    """
    关联表，用于建立 ResourceVersion 和 File 之间的多对多关系。
    """
    __tablename__ = 'ResourceVersionFileAssociation'
    resource_version_id = Column(String(36), ForeignKey('ResourceVersion.id'), primary_key=True)
    file_id = Column(String(36), ForeignKey('File.id'), primary_key=True)


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

    itemType = Column(String(20), nullable=False, default='resource', index=True)
    resourceType = Column(String(50), nullable=True, index=True)

    parentId = Column(String(36), ForeignKey("Resource.id"), nullable=True)
    sortOrder = Column(Integer, nullable=False, default=0)

    latestVersionId = Column(String(36), ForeignKey("ResourceVersion.id"), nullable=True)

    versions = relationship(
        "ResourceVersion",
        back_populates="resource",
        cascade="all, delete-orphan",
        order_by="ResourceVersion.sortOrder.asc()",
        # MODIFIED: 明确指定此关系使用 ResourceVersion.resourceId 作为外键
        foreign_keys="[ResourceVersion.resourceId]"
    )
    # 这个关系已经通过 foreign_keys=[latestVersionId] 明确指定了，所以是正确的
    latest_version = relationship("ResourceVersion", foreign_keys=[latestVersionId])

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
        # MODIFIED: 明确指定此反向关系使用本表(ResourceVersion)的 resourceId 字段
        foreign_keys=[resourceId]
    )
    associated_files = relationship("File", secondary="ResourceVersionFileAssociation")

