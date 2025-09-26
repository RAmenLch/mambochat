# backend/models.py

from sqlalchemy import Column, String, TEXT, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base
import uuid

# 使用 text 类型作为 UUID 的存储方式，兼容性更好
# 并提供一个默认的 uuid 生成函数
def generate_uuid():
    return str(uuid.uuid4())

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
    name = Column(String(100), nullable=False)   # e.g., "GPT-4o"
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
    systemPrompt = Column(TEXT, nullable=True)
    modelParameters = Column(TEXT, nullable=True)  # Store as JSON string
    aiModelId = Column(String(36), ForeignKey("AIModel.id"), nullable=True)

    # 关系：反向引用到 AIModel
    ai_model = relationship("AIModel", back_populates="chats")
    # 关系：一个 Chat 可以包含多条 Message
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "Message"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    content = Column(TEXT, nullable=False)
    createdAt = Column(DateTime, nullable=False, default=func.now())
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    chatId = Column(String(36), ForeignKey("Chat.id"), nullable=False)

    # 关系：反向引用到 Chat
    chat = relationship("Chat", back_populates="messages")

