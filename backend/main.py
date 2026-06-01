# backend/main.py

import asyncio
import os
import logging
from logging.handlers import RotatingFileHandler
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
    backend_management,
    api_client_router,
    system_log  # <-- 新增：导入系统日志路由
)
from backend.services.cleanup_service import cleanup_zombie_files
from backend.services.kb_service import SUP_DIM
from backend.services.vec_migration import ensure_vec_tables

scheduler = AsyncIOScheduler(timezone=TZ)

# 配置日志
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 支持通过环境变量控制日志级别，默认 INFO
# 可设置 MAMBO_LOG_LEVEL=DEBUG 来查看 embedding 等详细日志
_log_level_name = os.getenv("MAMBO_LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)

file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "mambochat.log"),
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
file_handler.setLevel(_log_level)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

logging.basicConfig(
    level=_log_level,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger("alembic")
logger.setLevel(_log_level)

def _get_db_head_revision(alembic_config):
    """获取 Alembic head 版本号"""
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(alembic_config)
    return script.get_current_head()


def run_alembic_migrations():
    """
    以编程方式运行 Alembic 迁移。

    快速路径：如果数据库已是最新版本，直接返回，跳过 SQLAlchemy 引擎创建。
    """
    config_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_config = Config(config_path)
    script_location = os.path.join(os.path.dirname(__file__), "alembic")
    alembic_config.set_main_option("script_location", script_location)

    from backend.database import DATABASE_URL
    sync_url = DATABASE_URL.replace("+aiosqlite", "")

    # ── 快速路径：用原生 sqlite3 直接查 alembic_version ──
    try:
        import sqlite3
        db_path = sync_url.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            row = conn.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
            if row:
                current_rev = row[0]
                head_rev = _get_db_head_revision(alembic_config)
                if current_rev == head_rev:
                    logger.info(
                        f"Alembic 快速路径: 数据库已是最新版本 ({current_rev})，跳过迁移"
                    )
                    return
                else:
                    logger.info(f"Alembic 需要升级: {current_rev} -> {head_rev}")
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"Alembic 快速路径检查未通过，走常规流程: {e}")

    # ── 常规路径：需要引擎检查的三种场景 ──
    from sqlalchemy import create_engine, inspect
    check_engine = create_engine(sync_url)

    try:
        inspector = inspect(check_engine)

        has_alembic_table = inspector.has_table("alembic_version")

        if has_alembic_table:
            logger.info("发现 Alembic 版本表，执行常规迁移...")
            command.upgrade(alembic_config, "head")
        else:
            has_v1_1_3_tables = (
                inspector.has_table("AIProvider") and
                inspector.has_table("Chat")
            )
            if has_v1_1_3_tables:
                logger.info("检测到已有 v1.1.3 数据库结构（未初始化 Alembic）")
                logger.info("正在标记基线版本 4442b0f1e406 ...")
                command.stamp(alembic_config, "4442b0f1e406")
                command.upgrade(alembic_config, "head")
            else:
                logger.info("检测到全新数据库，执行完整迁移...")
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
        await ensure_vec_tables(conn, dimensions=SUP_DIM)
        await conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunk_fts USING fts5(content_tokens);"))

    # 定时任务
    scheduler.add_job(cleanup_zombie_files, 'interval', hours=1)
    scheduler.start()

    yield

    # --- 应用关闭时执行 ---
    scheduler.shutdown()
    await close_checkpointer()


app = FastAPI(lifespan=lifespan, version="1.2.5")

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
app.include_router(backend_management.router,prefix="/api",tags=["Backend Management"])
app.include_router(api_client_router.router, prefix="/api", tags=["API Client"])

@app.get("/")
async def root():
    return {"message": "LLM-API Client Backend is running."}

