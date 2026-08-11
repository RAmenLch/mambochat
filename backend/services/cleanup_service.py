# backend/services/cleanup_service.py

import asyncio
import logging
import os
import sqlite3
import threading
import time as _time
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sqlalchemy import delete as sa_delete, func as sa_func

from backend.database import AsyncSessionLocal
from backend.models import file_model, chat_model, setting_model, resource_model, agent_model, log_model
from backend.schemas.enums import FileManagementType, ResourceType
from backend.services.file_service import FileService
from backend.services.stream_manager_service import stream_manager
from backend.services import maintenance
from backend.checkpointer import CHECKPOINTER_DB_FILE
from backend.config.timezone_config import get_configured_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORARY_FILE_LIFETIME = timedelta(hours=24)
LOG_MAX_ROWS = 10_000
VACUUM_FREELIST_THRESHOLD_BYTES = 1024 * 1024 * 1024  # 空闲页超过 1GB 才执行 VACUUM

# --- checkpoints.db 清理状态(供前端轮询进度) ---
_checkpoint_cleanup_state = {
    "status": "idle",          # idle | running | done | failed | skipped
    "stage": "",               # checking | vacuuming
    "progress": 0.0,           # 0-100
    "message": "",
    "reclaimable_bytes": 0,
    "freed_bytes": 0,
    "started_at": None,
    "finished_at": None,
}


def _probe_checkpoints_freelist_bytes() -> int:
    """探测 checkpoints.db 当前可回收的空闲字节数（不执行 VACUUM）。"""
    try:
        conn = sqlite3.connect(str(CHECKPOINTER_DB_FILE.resolve()), timeout=2, isolation_level=None)
        try:
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
            return freelist * page_size
        finally:
            conn.close()
    except Exception:
        return 0


def get_checkpoint_cleanup_status() -> dict:
    """返回当前 checkpoints.db 清理状态（含可回收量），供状态接口轮询。"""
    state = dict(_checkpoint_cleanup_state)
    if state["status"] == "idle":
        state["reclaimable_bytes"] = _probe_checkpoints_freelist_bytes()
    return state


async def _cleanup_temporary_files(db: AsyncSession):
    """清理过期的临时文件"""
    cutoff_time = get_configured_now() - TEMPORARY_FILE_LIFETIME

    # 查找包含 temporary 类型的文件
    stmt = select(file_model.File).where(
        file_model.File.management_type.contains([FileManagementType.TEMPORARY.value]),
        file_model.File.created_at < cutoff_time
    )
    result = await db.execute(stmt)
    expired_files = result.scalars().all()

    if not expired_files:
        return

    logger.info(f"发现 {len(expired_files)} 个过期的临时文件，准备清理...")
    file_service = FileService(db)

    for f in expired_files:
        try:
            deleted = await file_service.remove_type_and_cleanup(f.id, FileManagementType.TEMPORARY.value)
            if deleted:
                logger.info(f"已删除临时文件: {f.filename} (ID: {f.id})")
            else:
                logger.info(f"已移除文件 {f.filename} (ID: {f.id}) 的临时类型标记")
        except Exception as e:
            logger.error(f"处理临时文件 {f.id} 时出错: {e}")


async def _cleanup_sub_message_files(db: AsyncSession):
    """清理与任何 SubMessage 都不再关联的文件"""
    # 获取所有正在被 SubMessage 引用的文件ID
    stmt_active = select(chat_model.SubMessage.content).where(
        chat_model.SubMessage.type == 'File'
    ).distinct()
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    # 获取所有包含 sub_message 类型的文件ID
    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.SUB_MESSAGE.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    # 找出差集，即孤儿文件
    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 SubMessage 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.SUB_MESSAGE.value)
            if deleted:
                logger.info(f"已删除孤儿 SubMessage 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的 sub_message 类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 SubMessage 文件 {file_id} 时出错: {e}")


async def _cleanup_global_setting_files(db: AsyncSession):
    """清理与任何全局设置（如头像）都不再关联的文件"""
    avatar_keys = ["user_avatar_file_id", "ai_avatar_file_id"]
    stmt_active = select(setting_model.GlobalSettings.value).where(
        setting_model.GlobalSettings.key.in_(avatar_keys),
        setting_model.GlobalSettings.value.isnot(None)
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.GLOBAL_SETTING.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 GlobalSetting 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.GLOBAL_SETTING.value)
            if deleted:
                logger.info(f"已删除孤儿 GlobalSetting 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的 global_setting 类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 GlobalSetting 文件 {file_id} 时出错: {e}")


async def _cleanup_resource_files(db: AsyncSession):
    """清理与任何 ResourceVersion 都不再关联的 RESOURCE 类型文件"""
    stmt_active = (
        select(resource_model.ResourceVersion.content)
        .join(resource_model.Resource, resource_model.ResourceVersion.resourceId == resource_model.Resource.id)
        .where(
            resource_model.Resource.resourceType.in_([ResourceType.FILE.value, ResourceType.KB_FILE.value]),
            resource_model.ResourceVersion.content.is_not(None)
        )
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.RESOURCE.value]) |
        file_model.File.management_type.contains([FileManagementType.KB_DOCUMENT.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 Resource/KB 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.RESOURCE.value)

            if not deleted:
                deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.KB_DOCUMENT.value)

            if deleted:
                logger.info(f"已删除孤儿 Resource/KB 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的资源类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 Resource 文件 {file_id} 时出错: {e}")


async def _cleanup_agent_avatar_files(db: AsyncSession):
    """清理与任何 Agent 都不再关联的 AGENT_AVATAR 类型文件"""
    stmt_active = select(agent_model.Agent.agentAvatarId).where(
        agent_model.Agent.agentAvatarId.isnot(None)
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.AGENT_AVATAR.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 Agent 头像文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.AGENT_AVATAR.value)
            if deleted:
                logger.info(f"已删除孤儿 Agent 头像文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的 agent_avatar 类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 Agent 头像文件 {file_id} 时出错: {e}")


async def _cleanup_post_logs(db: AsyncSession):
    """清理过期的 LLM 报文日志：删除已不存在会话的孤儿日志，并保留最新 LOG_MAX_ROWS 条"""
    # 1. 删除 chatId 指向已删除会话的孤儿日志
    stmt_active_chats = select(chat_model.Chat.id)
    result_active = await db.execute(stmt_active_chats)
    active_chat_ids = {row[0] for row in result_active}

    stmt_orphan_logs = select(log_model.MamboPostLog.id).where(
        log_model.MamboPostLog.chatId.isnot(None),
        ~log_model.MamboPostLog.chatId.in_(active_chat_ids)
    )
    result_orphan = await db.execute(stmt_orphan_logs)
    orphan_log_ids = [row[0] for row in result_orphan]

    if orphan_log_ids:
        logger.info(f"发现 {len(orphan_log_ids)} 条孤儿会话日志，准备清理...")
        await db.execute(
            sa_delete(log_model.MamboPostLog).where(log_model.MamboPostLog.id.in_(orphan_log_ids))
        )
        await db.commit()
        logger.info(f"已删除 {len(orphan_log_ids)} 条孤儿会话日志")

    # 2. 限制总行数，仅保留最新的 LOG_MAX_ROWS 条
    count_stmt = select(sa_func.count()).select_from(log_model.MamboPostLog)
    count_result = await db.execute(count_stmt)
    total_rows = count_result.scalar() or 0

    if total_rows > LOG_MAX_ROWS:
        excess = total_rows - LOG_MAX_ROWS
        logger.info(f"日志总数 {total_rows} 超过上限 {LOG_MAX_ROWS}，准备清理最早的 {excess} 条...")

        # 找到需要保留的最早的边界时间点（即第 LOG_MAX_ROWS 条的时间）
        boundary_stmt = (
            select(log_model.MamboPostLog.createdAt)
            .order_by(log_model.MamboPostLog.createdAt.desc())
            .offset(LOG_MAX_ROWS - 1)
            .limit(1)
        )
        boundary_result = await db.execute(boundary_stmt)
        boundary_row = boundary_result.first()

        if boundary_row:
            boundary_time = boundary_row[0]
            delete_stmt = sa_delete(log_model.MamboPostLog).where(
                log_model.MamboPostLog.createdAt <= boundary_time
            )
            await db.execute(delete_stmt)
            await db.commit()
            logger.info(f"已清理 {excess} 条过期日志，保留最新 {LOG_MAX_ROWS} 条")


def _vacuum_checkpoints_db_sync(db_path: str, progress_cb=None) -> bool:
    """同步执行 checkpoints.db 的 WAL checkpoint 与 VACUUM(在线程中运行)。

    返回是否实际执行了 VACUUM；空闲页低于阈值时跳过。
    busy_timeout 设为 2 秒：业务活跃（拿不到排他锁）时快速放弃，让位业务。
    progress_cb 用于报告进度：通过 WAL 文件增长量估算 VACUUM 进度（0-100）。
    """
    conn = sqlite3.connect(db_path, timeout=2, isolation_level=None)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        free_bytes = freelist * page_size
        if free_bytes < VACUUM_FREELIST_THRESHOLD_BYTES:
            logger.info(
                f"checkpoints.db 空闲页 {free_bytes / 1024 / 1024:.0f} MB,"
                f"低于阈值 {VACUUM_FREELIST_THRESHOLD_BYTES / 1024 / 1024:.0f} MB,跳过 VACUUM"
            )
            return False
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        expected_new_bytes = max((page_count - freelist) * page_size, 1)

        stop_event = threading.Event()

        def _monitor_progress():
            while not stop_event.is_set():
                try:
                    wal_bytes = os.path.getsize(db_path + "-wal")
                    progress = min(wal_bytes / expected_new_bytes, 1.0) * 100
                    if progress_cb:
                        progress_cb(progress)
                except Exception:
                    pass
                _time.sleep(2)

        monitor = threading.Thread(target=_monitor_progress, daemon=True)
        monitor.start()
        try:
            logger.info(f"checkpoints.db 空闲页 {free_bytes / 1024 / 1024:.0f} MB,开始 VACUUM ...")
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.execute("VACUUM")
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                logger.warning("checkpoints.db 被业务占用，VACUUM 放弃，下轮重试")
                return False
            raise
        finally:
            stop_event.set()
        if progress_cb:
            progress_cb(100)
        logger.info(f"checkpoints.db VACUUM 完成,预计回收约 {free_bytes / 1024 / 1024:.0f} MB")
        return True
    finally:
        conn.close()


async def _run_vacuum_background() -> None:
    """后台执行 checkpoints.db VACUUM 并维护清理状态（供手动/自动共用）。"""
    db_path = str(CHECKPOINTER_DB_FILE.resolve())
    size_before = os.path.getsize(db_path)
    try:
        def progress_cb(p: float) -> None:
            _checkpoint_cleanup_state.update(stage="vacuuming", progress=round(p, 1))

        done = await asyncio.to_thread(_vacuum_checkpoints_db_sync, db_path, progress_cb)
        if done:
            size_after = os.path.getsize(db_path)
            _checkpoint_cleanup_state.update(
                status="done", stage="", progress=100,
                freed_bytes=max(size_before - size_after, 0),
                message="清理完成",
                finished_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            _checkpoint_cleanup_state.update(
                status="skipped", stage="", progress=0,
                message="空闲页低于阈值，无需清理",
                finished_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
            )
    except Exception as e:
        logger.error(f"checkpoints.db VACUUM 失败: {e}", exc_info=True)
        _checkpoint_cleanup_state.update(
            status="failed", stage="", message=f"清理失败: {e}",
            finished_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    finally:
        maintenance.end_vacuum()


async def run_checkpoint_vacuum() -> dict:
    """触发 checkpoints.db VACUUM（后台执行），返回当前状态。

    手动触发与凌晨自动触发共用入口：
    - 已有清理在进行时直接返回当前状态；
    - 存在进行中的生成任务时标记 skipped；
    - 通过 maintenance 互斥标志告知生成入口等待/拒绝。
    """
    if _checkpoint_cleanup_state["status"] == "running":
        return _checkpoint_cleanup_state
    if stream_manager.running_tasks or stream_manager.active_streams:
        _checkpoint_cleanup_state.update(
            status="skipped", stage="", progress=0,
            message="存在进行中的生成任务，已跳过",
            finished_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return _checkpoint_cleanup_state
    if not maintenance.try_begin_vacuum():
        return _checkpoint_cleanup_state
    _checkpoint_cleanup_state.update(
        status="running", stage="checking", progress=0,
        message="", freed_bytes=0,
        started_at=_time.strftime("%Y-%m-%d %H:%M:%S"),
        finished_at=None,
    )
    asyncio.create_task(_run_vacuum_background())
    return _checkpoint_cleanup_state


async def _vacuum_checkpoints_db() -> None:
    """凌晨窗口触发的自动 VACUUM（与手动触发共用执行逻辑）。"""
    await run_checkpoint_vacuum()


async def cleanup_zombie_files():
    """主清理函数，按顺序执行所有类型的僵尸文件清理。

    每项清理独立容错：单项失败仅记录日志，不阻塞后续清理任务。
    """
    logger.info("开始执行僵尸文件清理任务...")

    tasks = [
        ("过期临时文件", _cleanup_temporary_files),
        ("孤儿 SubMessage 文件", _cleanup_sub_message_files),
        ("孤儿 GlobalSetting 文件", _cleanup_global_setting_files),
        ("孤儿 Resource/KB 文件", _cleanup_resource_files),
        ("孤儿 Agent 头像文件", _cleanup_agent_avatar_files),
        ("孤儿/超限会话日志", _cleanup_post_logs),
    ]

    for name, task in tasks:
        try:
            async with AsyncSessionLocal() as db:
                await task(db)
        except Exception as e:
            logger.error(f"清理任务 [{name}] 执行失败，已跳过继续后续清理: {e}", exc_info=True)

    # checkpoints.db VACUUM：仅凌晨 3 点窗口执行（不依赖 DB 会话，独立容错）
    now = get_configured_now()
    if now.hour == 3 and now.minute < 10:
        await _vacuum_checkpoints_db()
    else:
        logger.info("非凌晨 3 点窗口，跳过 checkpoints.db VACUUM")

    logger.info("僵尸文件清理任务执行完毕。")
