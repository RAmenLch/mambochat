# backend/models/chat_model.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func, Integer, JSON
from sqlalchemy.orm import relationship
from backend.models.base_model import Base, generate_uuid
from backend.schemas.enums import MessageStatus, SubMessageType
from backend.config.timezone_config import get_configured_now
from backend.schemas.enums import ChatMode


class Chat(Base):
    __tablename__ = "Chat"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)

    itemType = Column(String(20), nullable=False, default='chat')  # 'chat' 或 'folder'
    parentId = Column(String(36), ForeignKey("Chat.id"), nullable=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    lastOpenedAt = Column(DateTime, nullable=True)

    systemPrompt = Column(TEXT, nullable=True)
    modelParameters = Column(TEXT, nullable=True)  # Store as JSON string
    aiModelId = Column(String(36), ForeignKey("AIModel.id"), nullable=True)
    chatMode = Column(String(20), nullable=False, default=ChatMode.NORMAL.value)
    agentId = Column(String(36), ForeignKey("Agent.id", ondelete="SET NULL"), nullable=True)

    # 关系: 反向引用到 Agent
    agent = relationship("Agent")
    # 资源挂载列表，存储资源ID的JSON数组
    resource_prompt_list = Column(JSON, nullable=True)

    # 启用的 MCP 服务 ID 列表，存储字符串数组
    enabled_mcp_ids = Column(JSON, nullable=True, default=list)

    # 关系: 反向引用到 AIModel
    ai_model = relationship("AIModel", back_populates="chats")
    # 关系: 一个 Chat 可以包含多条 Message
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

    # 关系: 自引用，用于构建文件夹层级结构
    children = relationship("Chat", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Chat", remote_side=[id], back_populates="children")


class Message(Base):
    __tablename__ = "Message"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    chatId = Column(String(36), ForeignKey("Chat.id"), nullable=False)

    # 树状结构与路由字段
    parentId = Column(String(36), ForeignKey("Message.id"), nullable=True)
    lastActiveAt = Column(DateTime, nullable=False, default=get_configured_now)
    sortOrder = Column(Integer, nullable=False) # 现在的语义变更为：记录节点在树中的深度层级

    # 关系: 反向引用到 Chat
    chat = relationship("Chat", back_populates="messages")
    # 关系: 一个 Message 包含多个 SubMessage
    sub_messages = relationship("SubMessage", back_populates="message", cascade="all, delete-orphan",
                                order_by="SubMessage.sortOrder")

    # 关系: 自引用，用于构建消息分支树
    children = relationship("Message", back_populates="parent")
    parent = relationship("Message", remote_side=[id], back_populates="children")


class SubMessage(Base):
    __tablename__ = "SubMessage"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    content = Column(TEXT, nullable=False)
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    messageId = Column(String(36), ForeignKey("Message.id"), nullable=False)
    sortOrder = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False, default=SubMessageType.NORMAL.value)
    config = Column(TEXT, nullable=True)  # Store as JSON string
    status = Column(String(20), nullable=False, default=MessageStatus.COMPLETED.value)

    # 关系: 反向引用到 Message
    message = relationship("Message", back_populates="sub_messages")
