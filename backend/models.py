# backend/models.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func, Integer
from sqlalchemy.orm import relationship
from .database import Base
import uuid
from enum import Enum


# 使用 text 类型作为 UUID 的存储方式，兼容性更好
def generate_uuid():
    return str(uuid.uuid4())


class MessageStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AIProvider(Base):
    __tablename__ = "AIProvider"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    apiHost = Column(String(255), nullable=False)
    apiKey = Column(String(255), nullable=False)

    # 关系：一个 Provider 可以有多个 Model
    models = relationship("AIModel", back_populates="provider", cascade="all, delete-orphan")


class AIModel(Base):
    __tablename__ = "AIModel"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    modelId = Column(String(100), nullable=False)  # e.g., "gpt-4o"
    name = Column(String(100), nullable=False)  # e.g., "GPT-4o"
    providerId = Column(String(36), ForeignKey("AIProvider.id"), nullable=False)

    # 关系：反向引用到 AIProvider
    provider = relationship("AIProvider", back_populates="models")
    # 关系：一个 Model 可以用于多个 Chat
    chats = relationship("Chat", back_populates="ai_model")


class Chat(Base):
    __tablename__ = "Chat"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    createdAt = Column(DateTime, nullable=False, default=func.now())

    # --- 字段，用于支持文件夹、排序和最近会话功能 ---
    itemType = Column(String(20), nullable=False, default='chat')  # 'chat' 或 'folder'
    parentId = Column(String(36), ForeignKey("Chat.id"), nullable=True)  # 父文件夹ID
    sortOrder = Column(Integer, nullable=False, default=0)  # 排序权重
    lastOpenedAt = Column(DateTime, nullable=True)  # 最后打开时间

    systemPrompt = Column(TEXT, nullable=True)
    modelParameters = Column(TEXT, nullable=True)  # Store as JSON string
    aiModelId = Column(String(36), ForeignKey("AIModel.id"), nullable=True)

    # 关系：反向引用到 AIModel
    ai_model = relationship("AIModel", back_populates="chats")
    # 关系：一个 Chat 可以包含多条 Message
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

    # 关系：自引用，用于构建文件夹层级结构
    children = relationship("Chat", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Chat", remote_side=[id], back_populates="children")


class Message(Base):
    __tablename__ = "Message"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    createdAt = Column(DateTime, nullable=False, default=func.now())
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    chatId = Column(String(36), ForeignKey("Chat.id"), nullable=False)
    sortOrder = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=MessageStatus.COMPLETED.value)  # 消息状态

    # 关系：反向引用到 Chat
    chat = relationship("Chat", back_populates="messages")
    # 关系：一个 Message 包含多个 SubMessage
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
    config = Column(TEXT, nullable=True)  # Store as JSON string, e.g., '{"is_collapsed": false}'

    # 关系：反向引用到 Message
    message = relationship("Message", back_populates="sub_messages")


class GlobalSettings(Base):
    __tablename__ = "GlobalSettings"

    key = Column(String(50), primary_key=True)
    value = Column(TEXT, nullable=True)

