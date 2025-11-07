# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import engine
from .models.base_model import Base
from .routers import (
    chat_management,
    chat_interaction,
    provider_management,
    provider_actions,
    settings,
    notifications,
    file_management
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # 在应用启动时，确保所有定义的模型表都已在数据库中创建
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan, version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含各个模块的路由
app.include_router(chat_management.router, prefix="/api", tags=["Chat Management"])
app.include_router(chat_interaction.router, prefix="/api", tags=["Chat Interaction"])
app.include_router(provider_management.router, prefix="/api", tags=["Provider & Model Management"])
app.include_router(provider_actions.router, prefix="/api", tags=["Provider Actions"])
app.include_router(settings.router, prefix="/api", tags=["Global Settings"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
# 新增文件管理路由，其前缀已在路由器内部定义
app.include_router(file_management.router)


@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}

