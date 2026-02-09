# backend/models/provider_model.py

from sqlalchemy import Column, String, ForeignKey, Boolean, TEXT
from sqlalchemy.orm import relationship
from backend.models.base_model import Base, generate_uuid
from backend.schemas.enums import ProviderWorkerType, ModelType

class AIProvider(Base):
    __tablename__ = "AIProvider"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    apiHost = Column(String(255), nullable=False)
    apiKey = Column(String(255), nullable=False)
    use_proxy = Column(Boolean, nullable=False, default=False)
    worker_type = Column(String(50), nullable=False, default=ProviderWorkerType.OPENAI.value)

    # 关系: 一个 Provider 可以有多个 Model
    models = relationship("AIModel", back_populates="provider", cascade="all, delete-orphan")


class AIModel(Base):
    __tablename__ = "AIModel"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    modelId = Column(String(100), nullable=False)  # e.g., "gpt-4o"
    name = Column(String(100), nullable=False)  # e.g., "GPT-4o"
    providerId = Column(String(36), ForeignKey("AIProvider.id"), nullable=False)
    meta_config = Column(TEXT, nullable=True) # 存储模型的元配置信息，如上下文长度、支持的参数等
    model_type = Column(String(50), nullable=False, default=ModelType.CHAT.value)

    # 关系: 反向引用到 AIProvider
    provider = relationship("AIProvider", back_populates="models")
    # 关系: 一个 Model 可以用于多个 Chat
    chats = relationship("Chat", back_populates="ai_model")
