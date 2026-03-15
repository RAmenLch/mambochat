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
from backend.models.chat_model import Message, SubMessage
from backend.schemas.enums import MessageRole, MessageStatus
from backend.checkpointer import init_checkpointer, close_checkpointer, adelete_thread
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
logger.setLevel(logging.INFO)

def run_alembic_migrations():
    """
    以编程方式运行 Alembic 迁移。
    相当于在命令行执行 `alembic upgrade head`。
    """
    config_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_config = Config(config_path)
    script_location = os.path.join(os.path.dirname(__file__), "alembic")
    alembic_config.set_main_option("script_location", script_location)

    logger.info("正在检查并应用数据库迁移...")
    command.upgrade(alembic_config, "head")
    logger.info("数据库迁移完成。")


async def cleanup_expired_checkpoints():
    """定时清理已完成且过期的底层 Agent 状态 (Checkpoints)"""
    cutoff_time = get_configured_now() - timedelta(days=7)
    async with AsyncSessionLocal() as db:
        stmt = select(Message.id).where(
            Message.role == MessageRole.ASSISTANT.value,
            Message.createdAt < cutoff_time
        )
        result = await db.execute(stmt)
        expired_message_ids = result.scalars().all()

        for msg_id in expired_message_ids:
            sub_stmt = select(SubMessage.id).where(
                SubMessage.messageId == msg_id,
                SubMessage.status.in_([MessageStatus.GENERATING.value, MessageStatus.PENDING_REVIEW.value])
            )
            sub_result = await db.execute(sub_stmt)
            active_subs = sub_result.scalars().first()

            if not active_subs:
                await adelete_thread(msg_id)


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
    scheduler.add_job(cleanup_expired_checkpoints, 'cron', hour=3)
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
