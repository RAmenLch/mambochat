import logging
from typing import Optional

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.database import get_db
from backend.models import group_chat_model
from backend.crud import group_chat_crud
from backend.services.group_chat import service as group_service
from backend.services.group_chat import generation_bridge

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# 创建与元信息
# ──────────────────────────────────────────────

@router.post(
    "/group-chats",
    response_model=schemas.GroupCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="原子创建群组会话",
)
async def create_group_chat(
    payload: schemas.GroupChatCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    原子创建群父节点、GroupState 和 N（N>2）个成员子会话。
    返回群与完整子节点，避免前端文件夹缓存误判为空。
    """
    return await group_service.create_group_chat(db, payload)


@router.get(
    "/group-chats/{group_id}",
    response_model=schemas.GroupDetailResponse,
    summary="获取群组元信息与运行状态",
)
async def get_group_chat(group_id: str, db: AsyncSession = Depends(get_db)):
    return await group_service.get_group_detail(db, group_id)


@router.patch(
    "/group-chats/{group_id}/settings",
    response_model=schemas.GroupControlResponse,
    summary="修改群组设置（自动轮次上限等）",
)
async def update_group_settings(
    group_id: str,
    payload: schemas.GroupSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await group_service.update_group_settings(db, group_id, payload)


@router.delete(
    "/group-chats/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="生命周期感知的整组删除",
)
async def delete_group_chat(group_id: str, db: AsyncSession = Depends(get_db)):
    await group_service.delete_group(db, group_id)
    return None


# ──────────────────────────────────────────────
# 群输入
# ──────────────────────────────────────────────

@router.post(
    "/group-chats/{group_id}/messages",
    response_model=schemas.GroupTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="接收群输入并按成员排队（空 recipientNames 表示广播）",
)
async def send_group_message(
    group_id: str,
    payload: schemas.GroupMessageSendRequest,
    db: AsyncSession = Depends(get_db),
):
    return await generation_bridge.enqueue_user_turn(
        db,
        group_id=group_id,
        content=payload.content,
        recipient_names=payload.recipientNames,
        request_id=payload.requestId,
    )


# ──────────────────────────────────────────────
# 邮件与任务分页
# ──────────────────────────────────────────────

def _mail_to_response(mail: group_chat_model.GroupMail) -> schemas.GroupMailResponse:
    return schemas.GroupMailResponse(
        id=mail.id,
        groupId=mail.groupId,
        sourceTaskId=mail.sourceTaskId,
        senderChatId=mail.senderChatId,
        senderAliasSnapshot=mail.senderAliasSnapshot,
        recipientSnapshot=mail.recipientSnapshot or [],
        title=mail.title,
        content=mail.content,
        state=mail.state,
        sequence=mail.sequence,
        createdAt=mail.createdAt,
        sentAt=mail.sentAt,
    )


@router.get(
    "/group-chats/{group_id}/mails",
    response_model=schemas.GroupMailListResponse,
    summary="按 sequence 游标分页获取已投递邮件",
)
async def list_group_mails(
    group_id: str,
    afterSequence: Optional[int] = Query(None, description="游标：返回 sequence 大于该值的邮件"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows = await group_chat_crud.list_sent_mail_page(db, group_id, afterSequence, limit)
    items = [_mail_to_response(m) for m in rows]
    next_after = items[-1].sequence if items else afterSequence
    return schemas.GroupMailListResponse(
        items=items,
        nextAfterSequence=next_after,
        hasMore=len(items) == limit,
    )


@router.get(
    "/group-chats/{group_id}/mail-reviews",
    response_model=schemas.GroupMailReviewResponse,
    summary="审核模式：待审核邮件与已决策邮件（被拒 / 已同意待投递）",
)
async def list_group_mail_reviews(group_id: str, db: AsyncSession = Depends(get_db)):
    return await group_service.get_group_mail_reviews(db, group_id)


@router.post(
    "/group-chats/{group_id}/mails/{mail_id}/approve",
    response_model=schemas.GroupMailDecisionResponse,
    summary="审核模式：同意投递该邮件",
)
async def approve_group_mail(
    group_id: str, mail_id: str, db: AsyncSession = Depends(get_db)
):
    return await group_service.decide_group_mail(db, group_id, mail_id, approve=True)


@router.post(
    "/group-chats/{group_id}/mails/{mail_id}/reject",
    response_model=schemas.GroupMailDecisionResponse,
    summary="审核模式：拒绝投递该邮件（拒绝原因必填）",
)
async def reject_group_mail(
    group_id: str,
    mail_id: str,
    payload: schemas.GroupMailRejectRequest,
    db: AsyncSession = Depends(get_db),
):
    return await group_service.decide_group_mail(
        db, group_id, mail_id, approve=False, reason=payload.reason
    )


def _task_to_response(task: group_chat_model.GroupTask) -> schemas.GroupTaskResponse:
    return schemas.GroupTaskResponse(
        id=task.id,
        groupId=task.groupId,
        memberChatId=task.memberChatId,
        sequence=task.sequence,
        kind=task.kind,
        state=task.state,
        requestId=task.requestId,
        userMessageId=task.userMessageId,
        assistantMessageId=task.assistantMessageId,
        attemptCount=task.attemptCount or 0,
        startedAt=task.startedAt,
        finishedAt=task.finishedAt,
        createdAt=task.createdAt,
        errorCode=task.errorCode,
        errorMessage=task.errorMessage,
    )


@router.get(
    "/group-chats/{group_id}/tasks",
    response_model=schemas.GroupTaskListResponse,
    summary="获取群组任务列表（激活/排队在前，终态历史在后）",
)
async def list_group_tasks(
    group_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(group_chat_model.GroupTask)
        .filter(group_chat_model.GroupTask.groupId == group_id)
        .order_by(group_chat_model.GroupTask.sequence.desc())
        .limit(limit)
    )
    tasks = list(result.scalars().all())
    return schemas.GroupTaskListResponse(
        items=[_task_to_response(t) for t in tasks],
        total=len(tasks),
    )


# ──────────────────────────────────────────────
# 控制
# ──────────────────────────────────────────────

@router.post(
    "/group-chats/{group_id}/pause",
    response_model=schemas.GroupControlResponse,
    summary="暂停后续调度（不等同取消当前生成）",
)
async def pause_group(group_id: str, db: AsyncSession = Depends(get_db)):
    return await group_service.pause_group(db, group_id)


@router.post(
    "/group-chats/{group_id}/resume",
    response_model=schemas.GroupControlResponse,
    summary="恢复可继续群（待审核/失败不能被普通 resume 越过）",
)
async def resume_group(group_id: str, db: AsyncSession = Depends(get_db)):
    return await group_service.resume_group(db, group_id)


@router.post(
    "/group-chats/{group_id}/tasks/{task_id}/retry",
    response_model=schemas.GroupControlResponse,
    summary="恢复允许恢复的原轮次（不创建重复通知）",
)
async def retry_group_task(group_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    await generation_bridge.retry_task(db, group_id, task_id)
    state = await group_chat_crud.get_group_state(db, group_id)
    return schemas.GroupControlResponse(
        groupId=group_id, status=state.status, version=state.version
    )


@router.post(
    "/group-chats/{group_id}/tasks/{task_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    summary="取消 queued 或停止 running；按状态幂等处理",
)
async def cancel_group_task(group_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    await generation_bridge.cancel_task(db, group_id, task_id)
    return {"message": "Cancellation requested."}


@router.post(
    "/group-chats/{group_id}/tasks/{task_id}/discard",
    response_model=schemas.GroupControlResponse,
    summary="放弃失败/停止/中断轮次，丢弃待发箱，不撤回已发送邮件",
)
async def discard_group_task(group_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    await generation_bridge.discard_task(db, group_id, task_id)
    state = await group_chat_crud.get_group_state(db, group_id)
    return schemas.GroupControlResponse(
        groupId=group_id, status=state.status, version=state.version
    )


@router.post(
    "/group-chats/{group_id}/members/{member_chat_id}/process-unread",
    response_model=schemas.GroupTaskAccepted,
    summary="用户明确要求处理遗留未读，复用合并队列",
)
async def process_member_unread(
    group_id: str, member_chat_id: str, db: AsyncSession = Depends(get_db)
):
    task_id = await generation_bridge.enqueue_notice(db, group_id, member_chat_id)
    return schemas.GroupTaskAccepted(groupId=group_id, taskIds=[task_id])
