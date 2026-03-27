# backend/main.py

import asyncio
import os
import logging
from datetime import timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text, select

# --- Alembic 导入 ---
from alembic.config import Config
from alembic import command

from backend.config.timezone_config import TZ, get_configured_now
from backend.database import engine, AsyncSessionLocal
from backend.models.base_model import Base
from backend.checkpointer import init_checkpointer, close_checkpointer
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
    skill_management,
    agent_management,
    system_log  # <-- 新增：导入系统日志路由
)
from backend.services.cleanup_service import cleanup_zombie_files
from backend.services.kb_service import SUP_DIM

scheduler = AsyncIOScheduler(timezone=TZ)

# 配置日志
logging.basicConfig()
logger = logging.getLogger("alembic")
logger.setLevel(logging.INFO)

def run_alembic_migrations():
    """
    以编程方式运行 Alembic 迁移。

    智能处理三种场景：
    1. 已有 Alembic：直接执行 upgrade head
    2. 已有 v1.1.3 表结构但未初始化 Alembic：标记基线 4442b0f1e406 为已执行，然后执行后续迁移
    3. 全新数据库：执行完整迁移链（包含 baseline 建表）
    """
    config_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_config = Config(config_path)
    script_location = os.path.join(os.path.dirname(__file__), "alembic")
    alembic_config.set_main_option("script_location", script_location)

    # 构建同步数据库 URL 用于状态检查（去掉 async 驱动前缀）
    from backend.database import DATABASE_URL
    sync_url = DATABASE_URL.replace("+aiosqlite", "")

    # 使用同步引擎检查数据库状态
    from sqlalchemy import create_engine, inspect
    check_engine = create_engine(sync_url)

    try:
        inspector = inspect(check_engine)

        # 1. 检查 Alembic 版本表是否存在
        has_alembic_table = inspector.has_table("alembic_version")

        if has_alembic_table:
            # 场景1：Alembic 已正常初始化，直接执行迁移
            logger.info("发现 Alembic 版本表，执行常规迁移...")
            command.upgrade(alembic_config, "head")

        else:
            # 2. 检查是否已存在 v1.1.3 的表结构
            # 以 AIProvider 和 Chat 表同时存在作为 v1.1.3 的标志（可根据实际情况调整）
            has_v1_1_3_tables = (
                    inspector.has_table("AIProvider") and
                    inspector.has_table("Chat")
            )

            if has_v1_1_3_tables:
                # 场景2：数据库已有 v1.1.3 结构，但未初始化 Alembic
                logger.info("检测到已有 v1.1.3 数据库结构（未初始化 Alembic）")
                logger.info("正在标记基线版本 4442b0f1e406（跳过建表语句）...")

                # 关键：stamp 命令只记录版本号，不执行 SQL
                command.stamp(alembic_config, "4442b0f1e406")

                logger.info("基线版本已标记，继续执行后续迁移...")
                command.upgrade(alembic_config, "head")

            else:
                # 场景3：全新空数据库，执行完整迁移（包含 4442b0f1e406 的建表语句）
                logger.info("检测到全新数据库，执行完整迁移（包含基线建表）...")
                command.upgrade(alembic_config, "head")

        logger.info("数据库迁移完成。")

    except Exception as e:
        logger.error(f"数据库迁移过程中发生错误: {e}")
        raise
    finally:
        check_engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---

    try:
        await asyncio.to_thread(run_alembic_migrations)
    except Exception as e:
        print(f"CRITICAL: 数据库迁移失败: {e}")
        raise e

    # 初始化底层持久化 Checkpointer
    await init_checkpointer()

    async with engine.begin() as conn:
        dimensions = SUP_DIM
        for dim in dimensions:
            table_name = f"vec_dim_{dim}"
            stmt = text(f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(vector FLOAT[{dim}]);")
            await conn.execute(stmt)

        await conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunk_fts USING fts5(content_tokens);"))

    # 定时任务
    scheduler.add_job(cleanup_zombie_files, 'interval', hours=1)
    scheduler.start()

    yield

    # --- 应用关闭时执行 ---
    scheduler.shutdown()
    await close_checkpointer()


app = FastAPI(lifespan=lifespan, version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 挂载路由 ---
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
app.include_router(agent_management.router, prefix="/api", tags=["Agent Management"])
app.include_router(system_log.router, prefix="/api/logs", tags=["System Logs"])
app.include_router(file_management.router)


@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}

