"""共享 LangGraph BaseStore 管理。

mambo_agents 新版 StoreBackend 和 VersionStore 都依赖 LangGraph BaseStore 持久化。
使用独立的 store.db 文件，与 checkpointer 的 checkpoints.db 分离，避免文件级锁冲突。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import aiosqlite
from langgraph.store.base import PutOp
from langgraph.store.sqlite.aio import AsyncSqliteStore

from backend._cli_args import DATA_DIR as _CLI_DATA_DIR

if _CLI_DATA_DIR:
    STORE_DB_FILE = Path(_CLI_DATA_DIR).joinpath("DB/store.db")
else:
    STORE_DB_FILE = Path(os.path.dirname(__file__)).parent.joinpath("DB/store.db")
STORE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

_conn: Optional[aiosqlite.Connection] = None
_store_instance: Optional[AsyncSqliteStore] = None


async def init_store() -> None:
    """初始化共享的 AsyncSqliteStore 实例。

    使用独立的 store.db 文件，与 checkpointer 的 checkpoints.db 完全分离，
    避免 SQLite 文件级锁互相阻塞。

    应在 FastAPI lifespan 启动阶段调用。
    """
    global _conn, _store_instance
    if _store_instance is None:
        db_path = str(STORE_DB_FILE.resolve())
        conn = await aiosqlite.connect(db_path, isolation_level=None)
        store = AsyncSqliteStore(conn)
        await store.setup()
        _conn = conn
        _store_instance = store


async def close_store() -> None:
    """关闭 Store 的数据库连接。

    应在 FastAPI lifespan 关闭阶段调用。
    """
    global _conn, _store_instance
    if _conn:
        await _conn.close()
        _conn = None
    _store_instance = None


def get_store() -> AsyncSqliteStore:
    """获取全局单例 AsyncSqliteStore 实例。

    供 Builder 和 Router 层注入 StoreBackend / VersionStore 使用。

    Raises:
        RuntimeError: Store 尚未初始化。
    """
    if _store_instance is None:
        raise RuntimeError("Store has not been initialized. Call init_store() first.")
    return _store_instance


async def adelete_thread_store(thread_id: str) -> None:
    """清理 LangGraph Store 中指定 thread 的全部数据。

    覆盖 StoreBackend 的 ``(thread_id, "mambo_fs")`` 会话工作区数据，以及
    VersionStore 的 ``(thread_id, "mambo_vc_blobs")`` / ``(thread_id, "mambo_vc_index")``
    版本控制数据。

    使用官方 BaseStore API：``alist_namespaces`` 枚举该 thread 的命名空间，
    ``asearch`` 分页枚举 key，``abatch(PutOp value=None)`` 批量删除。

    幂等：thread 无数据时静默返回；store 未初始化时静默返回。
    """
    if _store_instance is None:
        return

    namespaces = await _store_instance.alist_namespaces(prefix=(thread_id,), limit=1000)
    for ns in namespaces:
        keys: list[str] = []
        offset = 0
        while True:
            items = await _store_instance.asearch(ns, limit=100, offset=offset)
            if not items:
                break
            keys.extend(item.key for item in items)
            offset += len(items)
        # 分块删除，避免单条 SQL 参数数量超限
        for i in range(0, len(keys), 200):
            await _store_instance.abatch([PutOp(ns, k, None) for k in keys[i:i + 200]])
