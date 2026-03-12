# backend/main.py

import asyncio
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

# --- Alembic 导入 ---
from alembic.config import Config
from alembic import command

from backend.config.timezone_config import TZ
from backend.database import engine
# 注意：不再需要在启动时导入 Base 进行 create_all，但保留导入以防其他地方使用
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
    kb_management,
    skill_management
)
from backend.services.cleanup_service import cleanup_zombie_files
from backend.services.kb_service import SUP_DIM

scheduler = AsyncIOScheduler(timezone=TZ)

# 配置日志
logging.basicConfig()
logger = logging.getLogger("alembic")
logger.setLevel(logging.INFO)  # 确保能看到迁移日志

def run_alembic_migrations():
    """
    以编程方式运行 Alembic 迁移。
    相当于在命令行执行 `alembic upgrade head`。
    """
    # 获取 alembic.ini 的绝对路径 (假设 main.py 在 backend 目录下，alembic.ini 也在 backend 目录下)
    config_path = os.path.join(os.path.dirname(__file__), "alembic.ini")

    # 创建 Alembic 配置对象
    alembic_config = Config(config_path)

    # 关键：设置脚本位置。
    # 虽然 alembic.ini 里已经配了，但显式设置可以避免路径查找问题
    script_location = os.path.join(os.path.dirname(__file__), "alembic")
    alembic_config.set_main_option("script_location", script_location)

    logger.info("正在检查并应用数据库迁移...")

    # 执行升级到最新版本
    command.upgrade(alembic_config, "head")

    logger.info("数据库迁移完成。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---

    # 1. 核心：使用 Alembic 自动初始化/迁移数据库
    # 注意：这是一个阻塞操作，但在启动阶段是可接受的
    # 它会处理所有普通表（Chat, File, McpServer, McpTool 等）的创建和更新
    try:
        # 在线程池中运行同步的 Alembic 命令，避免阻塞事件循环（可选， startup 阶段通常直接跑也没问题）
        await asyncio.to_thread(run_alembic_migrations)
    except Exception as e:
        print(f"CRITICAL: 数据库迁移失败: {e}")
        # 如果迁移失败，通常不应该启动应用
        raise e

    # 2. 虚拟表初始化 (Alembic 忽略的部分)
    # 这些表由 sqlite-vec 和 FTS5 特殊逻辑管理，不通过 ORM 模型管理
    async with engine.begin() as conn:
        # 初始化预定义的向量表
        dimensions = SUP_DIM
        for dim in dimensions:
            table_name = f"vec_dim_{dim}"
            stmt = text(f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(vector FLOAT[{dim}]);")
            await conn.execute(stmt)

        # 初始化全文检索表 (FTS5)
        await conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunk_fts USING fts5(content_tokens);"))

    # 3. 定时任务
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
app.include_router(kb_management.router, prefix="/api/resources/kb", tags=["Knowledge Base Management"])
app.include_router(skill_management.router, prefix="/api/resources/skills", tags=["Skills Management"])
app.include_router(file_management.router)


@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}
