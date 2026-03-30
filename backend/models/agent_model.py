# backend/models/agent_model.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship

from backend.models.base_model import Base, generate_uuid
from backend.schemas.enums import AgentItemType, AgentTypeEnum
from backend.config.timezone_config import get_configured_now


class Agent(Base):
    """
    模型，用于存储 Agent 及其文件夹的配置信息与层级结构。
    """
    __tablename__ = "Agent"

    # 基础标识
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    description = Column(TEXT, nullable=True)

    # 树状层级控制
    itemType = Column(String(20), nullable=False, default=AgentItemType.AGENT.value)
    parentId = Column(String(36), ForeignKey("Agent.id"), nullable=True)
    sortOrder = Column(Integer, nullable=False, default=0)

    # 核心配置
    AgentType = Column(String(50), nullable=False, default=AgentTypeEnum.REACT.value)
    systemPrompt = Column(TEXT, nullable=True)
    modelParameters = Column(JSON, nullable=True)
    agentParameters = Column(JSON, nullable=True)

    # 关联配置
    aiModelId = Column(String(36), ForeignKey("AIModel.id", ondelete="SET NULL"), nullable=True)
    agentAvatarId = Column(String(36), nullable=True)

    resourcePromptList = Column(JSON, nullable=True)
    enabledMcpIds = Column(JSON, nullable=True)
    subAgents = Column(JSON, nullable=True)
    backendIds = Column(JSON, nullable=True)
    # 时间戳
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    updatedAt = Column(DateTime, nullable=False, default=get_configured_now, onupdate=get_configured_now)

    # ORM 关系
    children = relationship("Agent", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Agent", remote_side=[id], back_populates="children")

    # 单向关联配置查询
    ai_model = relationship("AIModel")
