# backend/database.py
import asyncio
import os

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from pathlib import Path

# --- 数据库配置 ---

# 修正点 1: 将文件名从 mambo.bat 改为 mambo.dat，与你的项目结构匹配
DATABASE_FILE = Path(os.path.dirname(__file__)).parent.joinpath("DB/mambo.dat")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_FILE.resolve()}" # 使用 .resolve() 确保路径正确

# --- SQLAlchemy 核心对象 ---

# 1. 创建异步数据库引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    # 修正点 2: 对于 aiosqlite, connect_args={"check_same_thread": False} 是不必要的，可以安全移除
)

# 2. 创建一个异步会话的工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 3. 创建一个声明式模型基类
Base = declarative_base()


# --- 依赖注入 ---
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# --- 数据库初始化函数 ---
async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
