# backend/services/group_chat/scheduler.py

"""
群组调度器。基于进程内 asyncio 循环 + 持久化 GroupTask 队列。

- 群内串行：同一群组同一时刻至多一个成员逻辑轮次；不同群组彼此独立。
- 群锁以数据库 GroupState.activeTaskId 为权威，进程内任务表仅用于去重与关闭协调。
- 启动时做崩溃恢复：running -> interrupted 并暂停受影响群；ready_to_commit 只补做邮箱提交。

首版基于现有内存 StreamManager 的单后端进程运行，不宣称多进程分布式协调。
"""

import asyncio
import contextlib
import logging
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import group_chat_model
from backend.crud import group_chat_crud
from backend.schemas.enums import (
    GroupStatus, GroupPauseReason, GroupTaskKind, GroupTaskState,
)
from backend.config.timezone_config import get_configured_now
from backend.services.group_chat import generation_bridge, mail_service, events
from backend.services.generation.core.outcome import GenerationOutcome

logger = logging.getLogger(__name__)


class GroupScheduler:
    TICK_SECONDS = 0.5

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._group_tasks: Dict[str, asyncio.Task] = {}

    # ── 生命周期 ──────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        await self.recover_on_startup()
        self._running = True
        self._loop_task = asyncio.create_task(self._loop())
        logger.info("[GroupScheduler] started")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._loop_task
            self._loop_task = None
        pending = list(self._group_tasks.values())
        for t in pending:
            t.cancel()
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._group_tasks.clear()
        logger.info("[GroupScheduler] stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[GroupScheduler] tick failed")
            await asyncio.sleep(self.TICK_SECONDS)

    # ── 调度 ──────────────────────────────────────

    async def _tick(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(group_chat_model.GroupState.groupId).filter(
                    group_chat_model.GroupState.status == GroupStatus.READY.value
                )
            )
            group_ids = [row[0] for row in result.all()]

        for group_id in group_ids:
            existing = self._group_tasks.get(group_id)
            if existing is not None and not existing.done():
                continue
            self._group_tasks[group_id] = asyncio.create_task(self._run_group(group_id))

    async def _run_group(self, group_id: str) -> None:
        try:
            while self._running:
                async with AsyncSessionLocal() as db:
                    task = await generation_bridge.claim_next_task(db, group_id)
                if task is None:
                    break
                outcome = await generation_bridge.run_group_task(group_id, task.id)
                if outcome is not GenerationOutcome.NORMAL_COMPLETED:
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[GroupScheduler] run_group failed for %s", group_id)
        finally:
            self._group_tasks.pop(group_id, None)

    # ── 崩溃恢复 ──────────────────────────────────

    async def recover_on_startup(self) -> None:
        """启动恢复：不自动重放有副作用的 running 生成。"""
        now = get_configured_now()

        # 1) running -> interrupted，并暂停受影响群
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(group_chat_model.GroupTask).filter(
                    group_chat_model.GroupTask.state == GroupTaskState.RUNNING.value
                )
            )
            running_tasks = list(result.scalars().all())
            affected = set()
            for task in running_tasks:
                task.state = GroupTaskState.INTERRUPTED.value
                task.finishedAt = now
                affected.add(task.groupId)
            for group_id in affected:
                state = await group_chat_crud.get_group_state(db, group_id)
                if state:
                    state.status = GroupStatus.PAUSED.value
                    state.pauseReason = GroupPauseReason.RESTART.value
                    state.activeTaskId = None
                    state.version = (state.version or 0) + 1
            if running_tasks or affected:
                await db.commit()
                for group_id in affected:
                    state = await group_chat_crud.get_group_state(db, group_id)
                    if state:
                        await events.publish_group_state_changed(
                            group_id, state.version, state.status, state.pauseReason
                        )

        # 2) ready_to_commit -> 只补做邮箱提交，不重新调用模型
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(group_chat_model.GroupTask).filter(
                    group_chat_model.GroupTask.state == GroupTaskState.READY_TO_COMMIT.value
                )
            )
            ready_tasks = list(result.scalars().all())
            for task in ready_tasks:
                state = await group_chat_crud.get_group_state(db, task.groupId)
                if state is None:
                    continue
                try:
                    sent = await mail_service.commit_group_turn(db, task, state)
                    for mail_id, sequence in sent:
                        await events.publish_group_mail_sent(
                            task.groupId, mail_id, sequence, version=state.version
                        )
                except Exception:
                    logger.exception("[GroupScheduler] ready_to_commit recovery failed for %s", task.id)
                    await db.rollback()


group_scheduler = GroupScheduler()
