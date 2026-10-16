# backend/services/group_chat/generation_bridge.py

"""
普通交互入口与群任务的适配层，以及群成员逻辑轮次的执行桥接。

职责：
- 把用户群输入 / 恢复请求转换为持久化 GroupTask；
- 在受控事务中抢占任务、冻结邮件快照、准备消息；
- 在群上下文中调用现有托管生成，取得独立 GenerationOutcome；
- 正常完成时提交邮箱事务，非正常结束时暂停群组。

本模块不重写模型适配器或 Agent 执行框架，只做编排。
"""

import logging
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.database import AsyncSessionLocal
from backend.models import chat_model, group_chat_model
from backend.crud import group_chat_crud, message_crud
from backend.schemas.enums import (
    MessageRole, MessageStatus, SubMessageType,
    GroupMailMode, GroupStatus, GroupPauseReason, GroupTaskKind, GroupTaskState, GroupMailState,
)
from backend.schemas.group_chat import normalize_member_alias, MASTER_ALIAS
from backend.config.timezone_config import get_configured_now
from backend.exceptions import AppHTTPException
from backend.services.stream_manager_service import stream_manager
from backend.services.group_chat import mail_service, events, service as group_service
from backend.services.group_chat.runtime import (
    GroupExecutionContext, set_group_context, reset_group_context,
)
from backend.services.generation.core.outcome import GenerationOutcome

logger = logging.getLogger(__name__)


class BridgeErrorCode:
    GROUP_NOT_FOUND = "GROUP_NOT_FOUND"
    NOT_RUNNABLE = "GROUP_NOT_RUNNABLE"
    UNKNOWN_RECIPIENT = "GROUP_UNKNOWN_RECIPIENT"
    IDEMPOTENCY_CONFLICT = "GROUP_IDEMPOTENCY_CONFLICT"


def _bad(code: str, detail: str, status: int = 400) -> AppHTTPException:
    return AppHTTPException(status_code=status, error_code=code, detail=detail)


# ──────────────────────────────────────────────
# 入队
# ──────────────────────────────────────────────

async def _existing_by_request(
    db: AsyncSession, group_id: str, request_id: str
) -> List[group_chat_model.GroupTask]:
    result = await db.execute(
        select(group_chat_model.GroupTask).filter(
            group_chat_model.GroupTask.groupId == group_id,
            group_chat_model.GroupTask.requestId == request_id,
        )
    )
    return list(result.scalars().all())


async def enqueue_user_turn(
    db: AsyncSession,
    group_id: str,
    content: str,
    recipient_names: Sequence[str],
    request_id: Optional[str] = None,
    attachment_file_ids: Optional[Sequence[str]] = None,
) -> schemas.GroupTaskAccepted:
    """
    用户群输入入队。空收件人=广播全部成员；非空则逐别名验证并去重。
    一次事务登记一封来自 Master 的邮件，并为每个目标成员登记邮件通知任务，失败整体回滚。
    attachment_file_ids：用户上传的中心库文件 ID，随邮件投递并注入各收件成员工作区。
    """
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(BridgeErrorCode.GROUP_NOT_FOUND, "group_not_found", 404)
    if state.status == GroupStatus.DELETING.value:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "group_deleting", 409)

    # 幂等：相同 requestId 直接返回既有任务，不重复创建
    if request_id:
        existing = await _existing_by_request(db, group_id, request_id)
        if existing:
            return schemas.GroupTaskAccepted(
                groupId=group_id,
                taskIds=[t.id for t in existing],
                state=GroupTaskState.QUEUED,
            )

    members = await group_chat_crud.list_member_chats(db, group_id)
    member_by_alias = {m.memberAlias: m for m in members if m.memberAlias}
    # 保留成员 Master（= 用户本人）不是生成目标：广播与显式 @ 都排除
    agent_members = [m for m in members if m.memberAlias != MASTER_ALIAS]

    if recipient_names:
        resolved: List[chat_model.Chat] = []
        seen = set()
        for raw in recipient_names:
            try:
                alias = normalize_member_alias(raw)
            except ValueError as e:
                raise _bad(BridgeErrorCode.UNKNOWN_RECIPIENT, f"invalid_recipient:{e}")
            if alias == MASTER_ALIAS:
                raise _bad(BridgeErrorCode.UNKNOWN_RECIPIENT, "cannot_target_user")
            member = member_by_alias.get(alias)
            if member is None:
                raise _bad(BridgeErrorCode.UNKNOWN_RECIPIENT, f"unknown_recipient:{alias}")
            if member.id in seen:
                continue
            seen.add(member.id)
            resolved.append(member)
        targets = resolved
    else:
        targets = agent_members

    if not targets:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "no_target_members")

    # 当前成员 sortOrder、id 排序后按 sequence FIFO
    targets = sorted(targets, key=lambda m: (m.sortOrder, m.id))

    # 确保用户成员 Master 存在，用于把本次用户发言记为「来自 Master 的邮件」
    master, _ = await group_service.ensure_master_member(db, group_id)

    # 用户上传的附件（中心库 fileId）：随邮件投递并注入各收件成员工作区
    file_ids = list(dict.fromkeys(
        f for f in (attachment_file_ids or []) if isinstance(f, str) and f
    ))

    # 用户本人发言 → 记为一封来自 Master 的已投递邮件；
    # 目标成员不再收到直接用户消息，改由邮件通知驱动（与成员间互发邮件一致）。
    user_mail, notice_tasks = await mail_service.record_user_mail(
        db, state, master, targets, content,
        attachments=await mail_service.build_attachment_refs_from_file_ids(db, file_ids),
        request_id=request_id,
    )

    state.version = (state.version or 0) + 1
    # 单次发起沟通：新的用户群输入开启新的额度周期，自动邮件轮次计数清零
    state.autoRoundCount = 0
    await db.commit()

    for task in notice_tasks:
        await events.publish_group_task_changed(
            group_id, task.id, task.memberChatId, GroupTaskState.QUEUED.value,
            version=state.version,
        )
    await events.publish_group_mail_sent(
        group_id, user_mail.id, user_mail.sequence, version=state.version
    )
    return schemas.GroupTaskAccepted(groupId=group_id, taskIds=[t.id for t in notice_tasks])


async def enqueue_member_turn(
    db: AsyncSession,
    group_id: str,
    member_chat_id: str,
    kind: str,
    payload: dict,
    base_message_id: Optional[str] = None,
    assistant_message_id: Optional[str] = None,
    request_id: Optional[str] = None,
    new_episode: bool = False,
) -> str:
    """
    为单个成员入队一个任务（用于子会话页直接发起、重生成、编辑重发、恢复）。
    恢复/重试复用既有 assistant 消息时不新建轮次。
    `new_episode=True` 表示用户在该子会话直接发起新一轮对话，会开启新的自动轮次额度周期。
    """
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(BridgeErrorCode.GROUP_NOT_FOUND, "group_not_found", 404)
    if state.status == GroupStatus.DELETING.value:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "group_deleting", 409)

    if request_id:
        existing = await _existing_by_request(db, group_id, request_id)
        if existing:
            return existing[0].id

    # 恢复原轮次：同一 assistant 消息已有等待/中断任务时复用，不新增轮次、不重复计自动轮次
    if assistant_message_id:
        result = await db.execute(
            select(group_chat_model.GroupTask).filter(
                group_chat_model.GroupTask.groupId == group_id,
                group_chat_model.GroupTask.memberChatId == member_chat_id,
                group_chat_model.GroupTask.assistantMessageId == assistant_message_id,
                group_chat_model.GroupTask.state.in_(
                    [GroupTaskState.WAITING_REVIEW.value, GroupTaskState.WAITING_USER.value]
                ),
            )
        )
        waiting = result.scalars().first()
        if waiting is not None:
            waiting.state = GroupTaskState.QUEUED.value
            waiting.finishedAt = None
            state.activeTaskId = None
            state.status = GroupStatus.READY.value
            state.pauseReason = None
            state.version = (state.version or 0) + 1
            await db.commit()
            await events.publish_group_task_changed(
                group_id, waiting.id, member_chat_id, GroupTaskState.QUEUED.value, version=state.version
            )
            return waiting.id

    seq = state.nextTaskSeq or 0
    state.nextTaskSeq = seq + 1
    task = group_chat_model.GroupTask(
        groupId=group_id,
        memberChatId=member_chat_id,
        sequence=seq,
        kind=kind,
        state=GroupTaskState.QUEUED.value,
        requestId=request_id,
        payload=payload,
        baseMessageId=base_message_id,
        assistantMessageId=assistant_message_id,
        attemptCount=0,
        createdAt=get_configured_now(),
    )
    db.add(task)
    await db.flush()
    # 用户在该子会话上的显式操作视为驱动该群继续：拉回可调度态
    state.status = GroupStatus.READY.value
    state.pauseReason = None
    state.activeTaskId = None
    if new_episode:
        # 直接发起新对话：开启新的自动轮次额度周期
        state.autoRoundCount = 0
    state.version = (state.version or 0) + 1
    await db.commit()
    await events.publish_group_task_changed(
        group_id, task.id, member_chat_id, GroupTaskState.QUEUED.value, version=state.version
    )
    return task.id


# ──────────────────────────────────────────────
# 抢占
# ──────────────────────────────────────────────

async def claim_next_task(
    db: AsyncSession, group_id: str
) -> Optional[group_chat_model.GroupTask]:
    """
    在可运行且无活动轮次时，选最早 queued 任务，短事务抢占。
    冻结邮件快照；mail_notice 无未读时标 skipped。
    返回被抢占任务；无任务/跳过则返回 None。
    """
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state or state.status != GroupStatus.READY.value or state.activeTaskId:
        return None

    tasks = await group_chat_crud.list_tasks_by_state(
        db, group_id, [GroupTaskState.QUEUED.value]
    )
    if not tasks:
        return None
    task = tasks[0]

    receipt_ids = await mail_service.freeze_snapshot(db, task)

    if task.kind == GroupTaskKind.MAIL_NOTICE.value and not receipt_ids:
        # 轮到执行时已无未读：不写空通知、不调用模型、不计自动轮次
        task.state = GroupTaskState.SKIPPED.value
        task.coalesceKey = None
        task.finishedAt = get_configured_now()
        state.version = (state.version or 0) + 1
        await db.commit()
        return None

    if task.kind == GroupTaskKind.MAIL_NOTICE.value and (
        state.autoRoundCount or 0
    ) >= (state.autoRoundLimit or 0):
        # 达到自动轮次上限：停止自动执行并暂停，但不丢邮件
        state.status = GroupStatus.PAUSED.value
        state.pauseReason = GroupPauseReason.ROUND_LIMIT.value
        state.version = (state.version or 0) + 1
        await db.commit()
        await events.publish_group_state_changed(
            group_id, state.version, GroupStatus.PAUSED.value, GroupPauseReason.ROUND_LIMIT.value
        )
        return None

    task.state = GroupTaskState.RUNNING.value
    task.coalesceKey = None
    task.startedAt = get_configured_now()
    task.attemptCount = (task.attemptCount or 0) + 1
    state.activeTaskId = task.id
    if task.kind == GroupTaskKind.MAIL_NOTICE.value:
        state.autoRoundCount = (state.autoRoundCount or 0) + 1
    state.version = (state.version or 0) + 1
    await db.commit()
    await events.publish_group_task_changed(
        group_id, task.id, task.memberChatId, GroupTaskState.RUNNING.value, version=state.version
    )
    return task


# ──────────────────────────────────────────────
# 执行
# ──────────────────────────────────────────────

async def _collect_task_attachment_file_ids(
    db: AsyncSession, task: group_chat_model.GroupTask
) -> List[str]:
    """收集本次轮次要注入到收件人工作区的附件 fileId（去重、保序）。

    - mail_notice：来自本轮冻结快照内邮件的附件；
    - user_message：来自 payload["attachmentFileIds"]（用户在群输入框上传的文件）。
    """
    file_ids: List[str] = []
    if task.kind == GroupTaskKind.MAIL_NOTICE.value:
        mails = await mail_service.list_snapshot_mails(db, task)
        for mail in mails:
            file_ids.extend(mail_service.resolved_file_ids_of(mail))
    else:
        raw = (task.payload or {}).get("attachmentFileIds") or []
        if isinstance(raw, list):
            file_ids.extend(f for f in raw if isinstance(f, str) and f)

    seen = set()
    result: List[str] = []
    for fid in file_ids:
        if fid in seen:
            continue
        seen.add(fid)
        result.append(fid)
    return result


async def _ensure_task_messages(task_id: str) -> str:
    """在受控事务中创建/绑定用户消息与 assistant 占位，返回 assistant 消息 ID。

    若本轮携带附件（邮件附件 / 用户上传），把副本写入收件成员的工作区即可；
    不向该成员会话附加 File 子消息，由成员在需要时用自身工具读取。
    """
    from backend.services import generation_service

    async with AsyncSessionLocal() as db:
        task = await group_chat_crud.get_task(db, task_id)
        if task is None:
            raise _bad(BridgeErrorCode.NOT_RUNNABLE, "task_not_found", 404)
        if task.assistantMessageId:
            return task.assistantMessageId

        chat_id = task.memberChatId
        payload = task.payload or {}

        if task.kind in (GroupTaskKind.USER_MESSAGE.value, GroupTaskKind.MAIL_NOTICE.value):
            text = payload.get("content") or payload.get("prompt") or ""
            user_message = await message_crud.create_message(
                db,
                message=schemas.MessageCreate(
                    role=MessageRole.USER,
                    sub_messages=[
                        schemas.SubMessageCreate(
                            content=text,
                            sortOrder=0,
                            type=SubMessageType.NORMAL,
                            status=MessageStatus.COMPLETED,
                        )
                    ],
                ),
                chat_id=chat_id,
            )
            # 附件已上传到中心库：物化到收件成员 backend 工作区，由成员自行读取。
            attachment_file_ids = await _collect_task_attachment_file_ids(db, task)
            if attachment_file_ids:
                await mail_service.materialize_mail_attachments(
                    db, chat_id, attachment_file_ids
                )
            assistant = await generation_service.prepare_for_regeneration(
                db, chat_id=chat_id, base_message_id=user_message.id
            )
            task.userMessageId = user_message.id
        else:
            # regenerate / edit_regenerate：从既有消息分支新的 assistant 占位
            base = task.baseMessageId or task.userMessageId
            assistant = await generation_service.prepare_for_regeneration(
                db, chat_id=chat_id, base_message_id=base
            )

        task.assistantMessageId = assistant.id
        await db.commit()
        return assistant.id


_OUTCOME_TO_TASK_STATE = {
    GenerationOutcome.CANCELLED: GroupTaskState.CANCELLED.value,
    GenerationOutcome.FAILED: GroupTaskState.FAILED.value,
    GenerationOutcome.WAITING_REVIEW: GroupTaskState.WAITING_REVIEW.value,
    GenerationOutcome.WAITING_USER: GroupTaskState.WAITING_USER.value,
}

_OUTCOME_TO_PAUSE = {
    GenerationOutcome.CANCELLED: GroupPauseReason.CANCELLED.value,
    GenerationOutcome.FAILED: GroupPauseReason.FAILURE.value,
    GenerationOutcome.WAITING_REVIEW: GroupPauseReason.REVIEW.value,
    GenerationOutcome.WAITING_USER: GroupPauseReason.ASK_USER.value,
}


async def _finalize_task(group_id: str, task_id: str, outcome: GenerationOutcome) -> None:
    async with AsyncSessionLocal() as db:
        task = await group_chat_crud.get_task(db, task_id)
        state = await group_chat_crud.get_group_state(db, group_id)
        if task is None or state is None:
            return
        now = get_configured_now()

        if outcome is GenerationOutcome.NORMAL_COMPLETED:
            if (state.mailMode or GroupMailMode.AUTO.value) == GroupMailMode.REVIEW.value:
                # 审核模式：本轮不投递，邮件转待审核并暂停整群，等待用户逐封决定
                held = await mail_service.hold_for_review(db, task, state)
                logger.info(
                    "[GroupBridge] task %s held for mail review (%s mails)", task.id, held
                )
                await events.publish_group_task_changed(
                    group_id, task.id, task.memberChatId, task.state,
                    version=state.version, assistant_message_id=task.assistantMessageId,
                )
                await events.publish_group_state_changed(
                    group_id, state.version, state.status, state.pauseReason
                )
                return
            task.state = GroupTaskState.READY_TO_COMMIT.value
            task.finishedAt = now
            await db.commit()
            sent = await mail_service.commit_group_turn(db, task, state)
            await events.publish_group_task_changed(
                group_id, task.id, task.memberChatId, GroupTaskState.SUCCEEDED.value,
                version=state.version, assistant_message_id=task.assistantMessageId,
            )
            for mail_id, sequence in sent:
                await events.publish_group_mail_sent(group_id, mail_id, sequence, version=state.version)
            return

        # 非正常结束：不投递、不确认已读
        if outcome.is_waiting:
            task.state = _OUTCOME_TO_TASK_STATE[outcome]
            # 保留 activeTaskId 与快照，等待合法继续
            state.status = GroupStatus.PAUSED.value
            state.pauseReason = _OUTCOME_TO_PAUSE[outcome]
        else:
            task.state = _OUTCOME_TO_TASK_STATE[outcome]
            task.finishedAt = now
            state.status = GroupStatus.PAUSED.value
            state.pauseReason = _OUTCOME_TO_PAUSE[outcome]
            state.activeTaskId = None
        state.version = (state.version or 0) + 1
        await db.commit()
        await events.publish_group_task_changed(
            group_id, task.id, task.memberChatId, task.state, version=state.version
        )
        await events.publish_group_state_changed(
            group_id, state.version, state.status, state.pauseReason
        )


async def run_group_task(group_id: str, task_id: str) -> GenerationOutcome:
    """
    执行一个已被抢占的群任务：安装群上下文 -> 准备消息 -> 托管生成 -> 收尾。
    返回独立 GenerationOutcome。
    """
    from backend.services import generation_service

    token = set_group_context(None)
    lock_chat_id: Optional[str] = None
    try:
        async with AsyncSessionLocal() as db:
            task = await group_chat_crud.get_task(db, task_id)
            if task is None:
                return GenerationOutcome.FAILED
            member = await db.get(chat_model.Chat, task.memberChatId)
            task_state = await group_chat_crud.get_group_state(db, group_id)
            lock_chat_id = task.memberChatId
            recover_from_error = bool((task.payload or {}).get("recover_from_error"))
            ctx = GroupExecutionContext(
                task_id=task.id,
                group_id=group_id,
                member_chat_id=task.memberChatId,
                member_alias=(member.memberAlias if member else "") or "",
                assistant_message_id=task.assistantMessageId,
                mail_mode=(
                    (task_state.mailMode if task_state else None)
                    or GroupMailMode.AUTO.value
                ),
            )
        token = set_group_context(ctx)

        await stream_manager.try_acquire_generation_lock(lock_chat_id)
        assistant_id = await _ensure_task_messages(task_id)
        outcome = await generation_service.run_group_member_generation(
            lock_chat_id, assistant_id, recover_from_error=recover_from_error
        )
        await _finalize_task(group_id, task_id, outcome)
        return outcome
    except Exception as e:
        logger.exception("群任务执行失败: %s", e)
        await _finalize_task(group_id, task_id, GenerationOutcome.FAILED)
        return GenerationOutcome.FAILED
    finally:
        reset_group_context(token)
        if lock_chat_id:
            await stream_manager.release_generation_lock(lock_chat_id)


# ──────────────────────────────────────────────
# 控制操作
# ──────────────────────────────────────────────

async def enqueue_notice(db: AsyncSession, group_id: str, member_chat_id: str) -> str:
    """用户明确要求处理某成员遗留未读：复用合并队列登记 mail_notice。"""
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(BridgeErrorCode.GROUP_NOT_FOUND, "group_not_found", 404)
    if state.pauseReason in (
        GroupPauseReason.REVIEW.value,
        GroupPauseReason.ASK_USER.value,
    ):
        raise _bad("GROUP_RESUME_BLOCKED", "cannot_process_unread_while_paused", 409)
    task = await mail_service.ensure_notice_task(db, state, member_chat_id)
    state.status = GroupStatus.READY.value
    state.pauseReason = None
    state.version = (state.version or 0) + 1
    await db.commit()
    return task.id


async def retry_task(db: AsyncSession, group_id: str, task_id: str) -> None:
    """恢复允许恢复的原轮次：不改 assistant 消息、不新建通知、不重复计自动轮次。"""
    task = await group_chat_crud.get_task(db, task_id)
    if task is None or task.groupId != group_id:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "task_not_found", 404)
    state = await group_chat_crud.get_group_state(db, group_id)
    task.state = GroupTaskState.QUEUED.value
    task.finishedAt = None
    task.errorCode = None
    task.errorMessage = None
    if state:
        state.activeTaskId = None
        state.status = GroupStatus.READY.value
        state.pauseReason = None
        state.version = (state.version or 0) + 1
    await db.commit()


async def cancel_task(db: AsyncSession, group_id: str, task_id: str) -> None:
    """取消 queued 或停止 running；按状态幂等处理。"""
    task = await group_chat_crud.get_task(db, task_id)
    if task is None or task.groupId != group_id:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "task_not_found", 404)
    if task.state == GroupTaskState.QUEUED.value:
        task.state = GroupTaskState.CANCELLED.value
        task.finishedAt = get_configured_now()
        task.coalesceKey = None
        await db.commit()
    elif task.state == GroupTaskState.RUNNING.value and task.assistantMessageId:
        # 触发取消信号；运行循环结束后会以 CANCELLED 结果暂停群组
        await stream_manager.request_cancellation(task.assistantMessageId)


async def discard_task(db: AsyncSession, group_id: str, task_id: str) -> None:
    """放弃失败/停止/中断轮次：丢弃暂存邮件，不撤回已发送邮件，随后继续后续任务。"""
    task = await group_chat_crud.get_task(db, task_id)
    if task is None or task.groupId != group_id:
        raise _bad(BridgeErrorCode.NOT_RUNNABLE, "task_not_found", 404)
    await db.execute(
        update(group_chat_model.GroupMail)
        .where(
            group_chat_model.GroupMail.sourceTaskId == task_id,
            group_chat_model.GroupMail.state.in_(
                [GroupMailState.STAGED.value, GroupMailState.REVIEWING.value]
            ),
        )
        .values(state=GroupMailState.DISCARDED.value)
    )
    if task.state != GroupTaskState.SUCCEEDED.value:
        task.state = GroupTaskState.CANCELLED.value
    task.finishedAt = get_configured_now()
    state = await group_chat_crud.get_group_state(db, group_id)
    if state:
        state.activeTaskId = None
        state.status = GroupStatus.READY.value
        state.pauseReason = None
        state.version = (state.version or 0) + 1
    await db.commit()
