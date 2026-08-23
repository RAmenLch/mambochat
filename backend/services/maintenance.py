"""全局数据库维护互斥。

VACUUM 等长耗时维护操作会持有 SQLite 排他锁，与业务写入互斥。
生成入口在维护期间应等待或拒绝，避免撞锁报错。
"""

import asyncio

_vacuuming = False
_vacuum_done = asyncio.Event()
_vacuum_done.set()


def is_vacuuming() -> bool:
    """当前是否正在执行 VACUUM 维护。"""
    return _vacuuming


def try_begin_vacuum() -> bool:
    """尝试进入 VACUUM 维护状态；已有维护在进行时返回 False。"""
    global _vacuuming
    if _vacuuming:
        return False
    _vacuuming = True
    _vacuum_done.clear()
    return True


def end_vacuum() -> None:
    """结束 VACUUM 维护状态，唤醒等待方。"""
    global _vacuuming
    _vacuuming = False
    _vacuum_done.set()


async def wait_vacuum_finished(timeout: float = 60.0) -> bool:
    """等待当前 VACUUM 维护结束；返回是否已就绪（超时返回 False）。"""
    if not _vacuuming:
        return True
    try:
        await asyncio.wait_for(_vacuum_done.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
