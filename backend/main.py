# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text
from backend.config.timezone_config import TZ
from backend.database import engine
from backend.models.base_model import Base
from backend.routers import (
    chat_management,
    chat_interaction,
    provider_management,
    provider_actions,
    settings,
    notifications,
    file_management,
    resource_management,
    system_config,
    mcp_management,
    kb_management
)
from backend.services.cleanup_service import cleanup_zombie_files
from backend.services.kb_service import SUP_DIM

scheduler = AsyncIOScheduler(timezone=TZ)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---
    async with engine.begin() as conn:
        # 确保所有定义的模型表都已在数据库中创建
        # Base.metadata 包含了所有继承自 Base 的模型（包括 McpServer）
        await conn.run_sync(Base.metadata.create_all)

        # 以下是特殊用途的虚拟表的创建,普通表是不需要在此处创建的
        # 初始化预定义的向量表
        # 使用 sqlite-vec 的 vec0 模块创建虚拟表
        # 预创建维度: 384, 768, 1024, 1536, 2560, 3072, 4096
        dimensions = SUP_DIM
        for dim in dimensions:
            table_name = f"vec_dim_{dim}"
            # 创建虚拟表 SQL, vec0 自动处理 rowid
            stmt = text(f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(vector FLOAT[{dim}]);")
            await conn.execute(stmt)

        # 初始化全文检索表 (FTS5)
        # content_tokens 存储经过 jieba 预分词后的空格分隔字符串
        await conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunk_fts USING fts5(content_tokens);"))

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
app.include_router(resource_management.router, prefix="/api", tags=["Resource Management"])
app.include_router(chat_interaction.router, prefix="/api", tags=["Chat Interaction"])
app.include_router(provider_management.router, prefix="/api", tags=["Provider & Model Management"])
app.include_router(provider_actions.router, prefix="/api", tags=["Provider Actions"])
app.include_router(settings.router, prefix="/api", tags=["Global Settings"])
app.include_router(system_config.router, prefix="/api", tags=["System Configuration"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(mcp_management.router, prefix="/api/mcp", tags=["MCP Management"])
# 修改路由前缀，从 /api/kb 改为 /api/resource/kb
app.include_router(kb_management.router, prefix="/api/resources/kb", tags=["Knowledge Base Management"])
app.include_router(file_management.router)


@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}
