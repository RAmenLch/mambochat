# backend/checkpointer.py

import os
import aiosqlite
from pathlib import Path
from typing import Optional

# 直接引入 LangGraph 官方的 SQLite 异步 Checkpointer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# 定义独立的 SQLite 数据库文件路径，专门用于存储 Agent 状态
CHECKPOINTER_DB_FILE = Path(os.path.dirname(__file__)).parent.joinpath("DB/checkpoints.db")
CHECKPOINTER_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

_conn: Optional[aiosqlite.Connection] = None
_checkpointer_instance: Optional[AsyncSqliteSaver] = None


async def init_checkpointer():
    """
    初始化底层的持久化 Checkpointer。
    供 FastAPI 的 lifespan 在应用启动时调用。
    """
    global _conn, _checkpointer_instance
    if _conn is None:
        db_path = str(CHECKPOINTER_DB_FILE.resolve())
        _conn = await aiosqlite.connect(db_path)
        _checkpointer_instance = AsyncSqliteSaver(_conn)
        # 调用原生 setup() 确保表结构 (checkpoints, writes) 被正确创建
        await _checkpointer_instance.setup()


async def close_checkpointer():
    """
    关闭 Checkpointer 数据库连接。
    供 FastAPI 的 lifespan 在应用关闭时调用。
    """
    global _conn, _checkpointer_instance
    if _conn:
        await _conn.close()
        _conn = None
        _checkpointer_instance = None


def get_checkpointer() -> AsyncSqliteSaver:
    """
    获取全局单例的 Checkpointer 实例。
    供 Manager / Worker 构建 Agent 时注入使用。
    """
    if _checkpointer_instance is None:
        raise RuntimeError("Checkpointer has not been initialized. Call init_checkpointer() first.")
    return _checkpointer_instance


async def adelete_thread(thread_id: str):
    """
    清理指定对话的底层状态记录。
    直接调用 LangGraph 原生的 adelete_thread 方法，安全可靠。
    """
    if _checkpointer_instance:
        await _checkpointer_instance.adelete_thread(thread_id)

