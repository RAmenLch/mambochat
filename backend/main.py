# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

from .database import engine
from .models.base_model import Base
from .routers import (
    chat_management,
    chat_interaction,
    provider_management,
    provider_actions,
    settings,
    notifications,
    file_management,
    resource_management  # 新增: 导入资源管理路由
)
from .services.cleanup_service import cleanup_zombie_files

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Shanghai"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---
    async with engine.begin() as conn:
        # 确保所有定义的模型表都已在数据库中创建
        # 注意: 新的 resource_model 中的模型需要被 Base 正确识别
        await conn.run_sync(Base.metadata.create_all)

    # 添加并启动僵尸文件清理的定时任务
    scheduler.add_job(cleanup_zombie_files, 'interval', hours=1)
    scheduler.start()

    yield

    # --- 应用关闭时执行 ---
    scheduler.shutdown()


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
app.include_router(resource_management.router, prefix="/api", tags=["Resource Management"])  # 新增: 注册资源管理路由
app.include_router(chat_interaction.router, prefix="/api", tags=["Chat Interaction"])
app.include_router(provider_management.router, prefix="/api", tags=["Provider & Model Management"])
app.include_router(provider_actions.router, prefix="/api", tags=["Provider Actions"])
app.include_router(settings.router, prefix="/api", tags=["Global Settings"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(file_management.router)


@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}

