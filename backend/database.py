# backend/database.py
import os
import re

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from pathlib import Path

# --- 数据库配置 ---
DATABASE_FILE = Path(os.path.dirname(__file__)).parent.joinpath("DB/mambo.dat")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_FILE.resolve()}"  # 使用 .resolve() 确保路径正确

# 从环境变量读取配置，决定是否打印SQL语句，默认为False
# 在开发时可设置环境变量 DB_ECHO=True
SQLALCHEMY_ECHO = os.getenv("DB_ECHO", "False").lower() == "true"


# --- SQLite 自定义函数 ---
def regexp(expr, item):
    """
    SQLite REGEXP 实现，使用 Python 的 re 模块。
    用于在 SQLite 中支持 REGEXP 操作符。
    """
    if item is None:
        return False
    try:
        reg = re.compile(expr, re.IGNORECASE)
        return reg.search(str(item)) is not None
    except re.error:
        return False


# --- SQLAlchemy 核心对象 ---

# 1. 创建异步数据库引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=SQLALCHEMY_ECHO,
)

# 注册 SQLite 自定义函数
# 注意：对于异步引擎，我们需要监听 sync_engine 的 connect 事件
@event.listens_for(engine.sync_engine, "connect")
def register_custom_functions(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "create_function"):
        dbapi_connection.create_function("REGEXP", 2, regexp)


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
