# backend/database.py
import os
import re
import sys  # 需要导入 sys 用于打印错误
import sqlite_vec  # 导入 sqlite_vec
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# --- 数据库配置 ---
DATABASE_FILE = Path(os.path.dirname(__file__)).parent.joinpath("DB/mambo.dat")
# 确保父目录存在
DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_FILE.resolve()}"

# 从环境变量读取配置，决定是否打印SQL语句，默认为False
SQLALCHEMY_ECHO = os.getenv("DB_ECHO", "False").lower() == "true"


# --- SQLite 自定义函数 ---
def regexp(expr, item):
    """
    SQLite REGEXP 实现，使用 Python 的 re 模块。
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


# --- 核心修复：正确加载 sqlite-vec ---
@event.listens_for(engine.sync_engine, "connect")
def register_custom_functions(dbapi_connection, connection_record):
    """
    在连接建立时加载扩展。
    关键点：需要解包 aiosqlite 的连接对象，找到底层的 sqlite3 连接。
    """
    # 1. 尝试获取原生 sqlite3 连接
    # SQLAlchemy 的 AsyncAdapt_aiosqlite_connection 包装了 aiosqlite.Connection
    # aiosqlite.Connection 包装了 sqlite3.Connection

    # 第一层解包
    aiosqlite_conn = getattr(dbapi_connection, "_connection", None)
    # 第二层解包 (如果第一层解包成功) 或 直接使用 (如果没被包装)
    raw_conn = getattr(aiosqlite_conn, "_conn", None) if aiosqlite_conn else dbapi_connection

    # 2. 加载 sqlite-vec 扩展
    if raw_conn:
        try:
            # 必须显式开启扩展加载权限
            raw_conn.enable_load_extension(True)

            # 加载扩展
            sqlite_vec.load(raw_conn)

            # 加载完成后关闭权限 (安全最佳实践)
            raw_conn.enable_load_extension(False)

            # print("DEBUG: sqlite-vec loaded successfully.")
        except Exception as e:
            print(f"CRITICAL WARNING: Failed to load sqlite-vec extension: {e}", file=sys.stderr)
    else:
        print("CRITICAL WARNING: Could not access raw sqlite3 connection to load extensions.", file=sys.stderr)

    # 3. 启用 WAL 模式 (Write-Ahead Logging)
    # 这对于并发读写至关重要，避免 database is locked 错误
    try:
        # 这里可以使用 dbapi_connection，因为 cursor 方法通常被透传了
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")  # 进一步优化写入性能
        cursor.close()
    except Exception as e:
        print(f"Warning: Failed to set WAL mode: {e}")

    # 4. 注册 REGEXP 函数
    # 同样需要尝试在 raw_conn 上注册，或者检查 dbapi_connection 是否支持
    target_conn = raw_conn if raw_conn else dbapi_connection
    if hasattr(target_conn, "create_function"):
        try:
            target_conn.create_function("REGEXP", 2, regexp)
        except Exception as e:
            print(f"Warning: Failed to register REGEXP function: {e}")


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


