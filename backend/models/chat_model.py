# backend/models/chat_model.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func, Integer
from sqlalchemy.orm import relationship
from enum import Enum
from .base_model import Base, generate_uuid

class MessageStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Chat(Base):
    __tablename__ = "Chat"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    createdAt = Column(DateTime, nullable=False, default=func.now())

    itemType = Column(String(20), nullable=False, default='chat')  # 'chat' 或 'folder'
    parentId = Column(String(36), ForeignKey("Chat.id"), nullable=True)
    sortOrder = Column(Integer, nullable=False, default=0)
    lastOpenedAt = Column(DateTime, nullable=True)

    systemPrompt = Column(TEXT, nullable=True)
    modelParameters = Column(TEXT, nullable=True)  # Store as JSON string
    aiModelId = Column(String(36), ForeignKey("AIModel.id"), nullable=True)

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
    createdAt = Column(DateTime, nullable=False, default=func.now())
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    chatId = Column(String(36), ForeignKey("Chat.id"), nullable=False)
    sortOrder = Column(Integer, nullable=False)

    # 关系: 反向引用到 Chat
    chat = relationship("Chat", back_populates="messages")
    # 关系: 一个 Message 包含多个 SubMessage
    sub_messages = relationship("SubMessage", back_populates="message", cascade="all, delete-orphan",
                                order_by="SubMessage.sortOrder")


class SubMessage(Base):
    __tablename__ = "SubMessage"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    content = Column(TEXT, nullable=False)
    createdAt = Column(DateTime, nullable=False, default=func.now())
    messageId = Column(String(36), ForeignKey("Message.id"), nullable=False)
    sortOrder = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False, default="Normal")
    config = Column(TEXT, nullable=True)  # Store as JSON string
    status = Column(String(20), nullable=False, default=MessageStatus.COMPLETED.value)

    # 关系: 反向引用到 Message
    message = relationship("Message", back_populates="sub_messages")

