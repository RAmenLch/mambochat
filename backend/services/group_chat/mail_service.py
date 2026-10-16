# backend/services/group_chat/mail_service.py

"""
群组邮箱核心：地址解析、暂存、固定快照读取、确认与投递事务、自动通知合并。

关键不变量：
- sendMail 仅暂存（staged），正常完成后的提交事务才真正投递。
- readMails 每次只读启动时冻结的 snapshotReceiptIds；确认已读仅作用于该快照。
- 投递、收件记录、通知合并、任务置成功在同一事务中完成，保证“数据库投递一次”。
"""

import logging
from pathlib import PurePosixPath
from typing import List, Optional, Sequence, Tuple, Dict, Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import chat_model, group_chat_model
from backend.models.base_model import generate_uuid
from backend.crud import group_chat_crud
from backend.schemas.enums import (
    FileManagementType,
    GroupMailMode,
    GroupMailState,
    GroupPauseReason,
    GroupStatus,
    GroupTaskKind,
    GroupTaskState,
)
from backend.services.file_service import FileService
from backend.schemas.group_chat import normalize_member_alias, MASTER_ALIAS
from backend.exceptions import AppHTTPException
from backend.config.timezone_config import get_configured_now
from backend.services.group_chat.runtime import GroupExecutionContext

logger = logging.getLogger(__name__)


class MailErrorCode:
    EMPTY_RECIPIENTS = "GROUP_MAIL_EMPTY_RECIPIENTS"
    UNKNOWN_RECIPIENT = "GROUP_MAIL_UNKNOWN_RECIPIENT"
    IDEMPOTENCY_CONFLICT = "GROUP_MAIL_IDEMPOTENCY_CONFLICT"
    NO_CONTEXT = "GROUP_MAIL_NO_CONTEXT"
    MAIL_NOT_FOUND = "GROUP_MAIL_NOT_FOUND"
    INVALID_STATE = "GROUP_MAIL_INVALID_STATE"
    REJECT_REASON_REQUIRED = "GROUP_MAIL_REJECT_REASON_REQUIRED"


def _bad(code: str, detail: str, status: int = 400) -> AppHTTPException:
    return AppHTTPException(status_code=status, error_code=code, detail=detail)


# --- 附件 ---

# 单封邮件允许携带的附件数量上限
MAX_MAIL_ATTACHMENTS = 10

# 群组邮件附件写入收件成员 backend 工作区的根目录
GROUP_MAIL_FILE_DIR = "/.mambo/group_mail_file"


def normalize_attachment_paths(raw: Any) -> List[dict]:
    """把 sendMail 的 attachments（发件人工作区路径数组）规范化为去重后的引用列表。

    返回 [{path}]；空/非法项忽略，超过上限截断。
    """
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    normalized: List[str] = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        normalized.append(path)
        if len(normalized) >= MAX_MAIL_ATTACHMENTS:
            break
    return [{"path": p} for p in normalized]


def attachment_paths_of(mail: group_chat_model.GroupMail) -> List[str]:
    """读取邮件上已固化的原始附件路径（用于幂等比较）。"""
    return [
        a.get("path") for a in (mail.attachments or [])
        if isinstance(a, dict) and a.get("path")
    ]


def resolved_file_ids_of(mail: group_chat_model.GroupMail) -> List[str]:
    """读取邮件上已解析的附件中心库 fileId 列表。"""
    return [
        a.get("fileId") for a in (mail.attachments or [])
        if isinstance(a, dict) and a.get("fileId")
    ]


async def _download_and_store_attachment(db: AsyncSession, backend, path: str) -> dict:
    """从发件人 backend 下载工作区文件并入库为中心库文件，返回附件引用。"""
    from mambo_agents.backends.schemas import VirtualPath
    from mambo_agents.backends.protocol import _get_mime_type

    results = await backend.adownload_files([VirtualPath(path)])
    if not results:
        raise ValueError("download_empty_result")
    raw = results[0].content
    if not raw:
        err = getattr(results[0], "error", None)
        raise ValueError(f"download_failed:{err or 'empty_file'}")

    filename = PurePosixPath(path.replace("\\", "/")).name or "attachment"
    mime = _get_mime_type(path) or "application/octet-stream"
    fs = FileService(db)
    db_file = await fs.save_file_from_bytes(
        data=raw,
        filename=filename,
        mime_type=mime,
        management_type=[FileManagementType.GROUP_MAIL_ATTACHMENT.value],
        sub_path="group_mail_attachments",
    )
    return {
        "fileId": db_file.id,
        "filename": db_file.filename,
        "mimeType": db_file.mime_type,
        "sizeBytes": db_file.size,
        "path": path,
    }


async def resolve_attachment_refs(
    db: AsyncSession, sender_chat_id: str, items: Sequence[dict]
) -> List[dict]:
    """把 [{path}] 引用解析为中心库文件引用；下载失败降级为 {path, error}。

    同一发件人 backend 只构建一次；已含 fileId 的项原样保留（幂等）。
    """
    resolved: List[dict] = []
    backend = None
    backend_error: Optional[str] = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("fileId"):
            resolved.append(item)
            continue
        path = item.get("path")
        if not path:
            continue
        if backend is None and backend_error is None:
            try:
                from backend.services.generation.agent.backend_factory import (
                    build_backend_from_chat_id,
                )
                backend = await build_backend_from_chat_id(
                    db, sender_chat_id, thread_id=sender_chat_id
                )
            except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
                backend_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "[GroupMail] 构建发件人 backend 失败 chat=%s: %s", sender_chat_id, e
                )
        if backend is None:
            resolved.append({"path": path, "error": backend_error or "backend_unavailable"})
            continue
        try:
            resolved.append(await _download_and_store_attachment(db, backend, path))
        except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
            logger.warning(
                "[GroupMail] 附件下载失败 path=%s chat=%s: %s", path, sender_chat_id, e
            )
            resolved.append({"path": path, "error": f"{type(e).__name__}: {e}"[:200]})
    return resolved


# --- 地址解析 ---

async def resolve_recipients(
    db: AsyncSession, group_id: str, addresses: Sequence[str]
) -> List[Tuple[str, str]]:
    """
    将别名数组解析为 [(memberChatId, alias)]，去重并保留顺序。
    任一地址无效则整封拒绝，不部分发送。
    """
    normalized: List[str] = []
    seen = set()
    for raw in addresses or []:
        try:
            alias = normalize_member_alias(raw)
        except ValueError as e:
            raise _bad(MailErrorCode.UNKNOWN_RECIPIENT, f"invalid_address:{e}")
        if alias in seen:
            continue
        seen.add(alias)
        normalized.append(alias)

    if not normalized:
        raise _bad(MailErrorCode.EMPTY_RECIPIENTS, "empty_recipients")

    resolved: List[Tuple[str, str]] = []
    for alias in normalized:
        member = await group_chat_crud.find_member_by_alias(db, group_id, alias)
        if not member:
            raise _bad(MailErrorCode.UNKNOWN_RECIPIENT, f"unknown_recipient:{alias}")
        resolved.append((member.id, alias))
    return resolved


# --- 暂存 ---

async def _get_mail_by_toolcall(
    db: AsyncSession, task_id: str, tool_call_id: str
) -> Optional[group_chat_model.GroupMail]:
    result = await db.execute(
        select(group_chat_model.GroupMail).filter(
            group_chat_model.GroupMail.sourceTaskId == task_id,
            group_chat_model.GroupMail.toolCallId == tool_call_id,
        )
    )
    return result.scalars().first()


async def _next_tool_order(db: AsyncSession, task_id: str) -> int:
    result = await db.execute(
        select(func.max(group_chat_model.GroupMail.toolCallOrder)).filter(
            group_chat_model.GroupMail.sourceTaskId == task_id
        )
    )
    max_order = result.scalar()
    return (max_order if max_order is not None else -1) + 1


def _recipient_names(mail: group_chat_model.GroupMail) -> List[str]:
    return [r.get("memberName") for r in (mail.recipientSnapshot or [])]


async def stage_mail(
    db: AsyncSession,
    ctx: GroupExecutionContext,
    tool_call_id: str,
    addresses: Sequence[str],
    title: Optional[str],
    content: str,
    attachments: Optional[Sequence[str]] = None,
) -> group_chat_model.GroupMail:
    """
    暂存一封邮件。同一次工具调用重放返回同一暂存邮件；
    同 key 但参数不同则报幂等冲突，不覆盖原文。
    仅写 staged，不投递、不生成收件记录、不触发任务。
    attachments：发件人工作区路径数组，暂存时即下载入库为中心库文件引用。
    """
    if ctx is None:
        raise _bad(MailErrorCode.NO_CONTEXT, "group_context_required", 500)

    resolved = await resolve_recipients(db, ctx.group_id, addresses)
    new_snapshot = [
        {"memberChatId": cid, "memberName": alias} for cid, alias in resolved
    ]

    raw_items = normalize_attachment_paths(attachments)

    existing = await _get_mail_by_toolcall(db, ctx.task_id, tool_call_id)
    if existing is not None:
        if (
            _recipient_names(existing) != [alias for _, alias in resolved]
            or (existing.title or "") != (title or "")
            or existing.content != content
            or attachment_paths_of(existing) != [i["path"] for i in raw_items]
        ):
            raise _bad(MailErrorCode.IDEMPOTENCY_CONFLICT, "tool_call_id_conflict", 409)
        return existing

    attach_refs = (
        await resolve_attachment_refs(db, ctx.member_chat_id, raw_items)
        if raw_items else None
    )

    order = await _next_tool_order(db, ctx.task_id)
    mail = group_chat_model.GroupMail(
        groupId=ctx.group_id,
        sourceTaskId=ctx.task_id,
        senderChatId=ctx.member_chat_id,
        senderAliasSnapshot=ctx.member_alias,
        recipientSnapshot=new_snapshot,
        title=title,
        content=content,
        attachments=attach_refs,
        toolCallId=tool_call_id,
        toolCallOrder=order,
        state=GroupMailState.STAGED.value,
        createdAt=get_configured_now(),
    )
    db.add(mail)
    await db.flush()
    return mail


async def build_attachment_refs_from_file_ids(
    db: AsyncSession, file_ids: Optional[Sequence[str]]
) -> List[dict]:
    """把用户上传的中心库 fileId 列表整理为邮件附件引用（已解析态）。"""
    if not file_ids:
        return []
    from backend.crud import file_crud

    ordered = list(dict.fromkeys([f for f in file_ids if isinstance(f, str) and f]))
    files = await file_crud.get_files_by_ids(db, ordered)
    by_id = {f.id: f for f in files}
    refs: List[dict] = []
    for fid in ordered:
        f = by_id.get(fid)
        if f is None:
            continue
        refs.append({
            "fileId": f.id,
            "filename": f.filename,
            "mimeType": f.mime_type,
            "sizeBytes": f.size,
        })
        if len(refs) >= MAX_MAIL_ATTACHMENTS:
            break
    return refs


async def mail_attachments_response(
    db: AsyncSession, mail: group_chat_model.GroupMail
) -> List[dict]:
    """把邮件的附件引用整理为响应项（含下载 url），供前端展示。"""
    raw = [
        a for a in (mail.attachments or [])
        if isinstance(a, dict) and a.get("fileId")
    ]
    if not raw:
        return []
    from backend.crud import file_crud

    file_ids = [a["fileId"] for a in raw]
    files = await file_crud.get_files_by_ids(db, file_ids)
    fs = FileService(db)
    url_by_id = {f.id: fs.get_url(f.storage_path) for f in files}
    result: List[dict] = []
    for a in raw:
        fid = a["fileId"]
        result.append({
            "fileId": fid,
            "filename": a.get("filename"),
            "mimeType": a.get("mimeType"),
            "sizeBytes": a.get("sizeBytes"),
            "url": url_by_id.get(fid),
        })
    return result


async def record_user_mail(
    db: AsyncSession,
    group_state: group_chat_model.GroupState,
    master_chat: chat_model.Chat,
    recipients: Sequence[chat_model.Chat],
    content: str,
    title: Optional[str] = None,
    attachments: Optional[Sequence[dict]] = None,
    request_id: Optional[str] = None,
) -> Tuple[group_chat_model.GroupMail, List[group_chat_model.GroupTask]]:
    """
    把用户本人的群发言记为「一封来自 Master 的邮件」投递到邮件流。
    - 立即投递（sent），不受审核模式影响（用户即审核者）。
    - 收件记录保持「未读」，并为每个收件成员登记/合并 mail_notice，
      由邮件通知驱动收件成员读取（与成员间互发邮件一致），
      不再向成员子会话直接注入用户消息。
    返回 (mail, 本次涉及的通知任务列表)。
    """
    now = get_configured_now()
    seq = group_state.nextMailSeq or 0
    group_state.nextMailSeq = seq + 1

    mail = group_chat_model.GroupMail(
        groupId=group_state.groupId,
        sourceTaskId=generate_uuid(),
        senderChatId=master_chat.id,
        senderAliasSnapshot=MASTER_ALIAS,
        recipientSnapshot=[
            {"memberChatId": r.id, "memberName": r.memberAlias} for r in recipients
        ],
        title=title,
        content=content,
        attachments=list(attachments) if attachments else None,
        toolCallId=generate_uuid(),
        toolCallOrder=0,
        state=GroupMailState.SENT.value,
        sequence=seq,
        createdAt=now,
        sentAt=now,
    )
    db.add(mail)
    await db.flush()

    notices: List[group_chat_model.GroupTask] = []
    seen_task_ids = set()
    for r in recipients:
        receipt = group_chat_model.GroupMailReceipt(
            mailId=mail.id,
            recipientChatId=r.id,
            createdAt=now,
        )
        db.add(receipt)
        await db.flush()
        task = await enqueue_mail_notice(
            db, group_state, r.id, receipt, request_id=request_id
        )
        if task.id not in seen_task_ids:
            seen_task_ids.add(task.id)
            notices.append(task)
    await db.flush()
    return mail, notices


# --- 快照冻结与读取 ---

async def freeze_snapshot(
    db: AsyncSession, task: group_chat_model.GroupTask
) -> List[str]:
    """
    首次启动 task 时冻结全部已投递未读 receipt（按邮件 sequence 排序）。
    已冻结则原样返回，恢复原轮次时不重取。
    """
    if task.snapshotTakenAt is not None:
        return list(task.snapshotReceiptIds or [])

    result = await db.execute(
        select(group_chat_model.GroupMailReceipt.id)
        .join(
            group_chat_model.GroupMail,
            group_chat_model.GroupMail.id == group_chat_model.GroupMailReceipt.mailId,
        )
        .filter(
            group_chat_model.GroupMailReceipt.recipientChatId == task.memberChatId,
            group_chat_model.GroupMailReceipt.readAt.is_(None),
            group_chat_model.GroupMail.state == GroupMailState.SENT.value,
        )
        .order_by(group_chat_model.GroupMail.sequence.asc())
    )
    receipt_ids = [row[0] for row in result.all()]
    task.snapshotReceiptIds = receipt_ids
    task.snapshotTakenAt = get_configured_now()
    await db.flush()
    return receipt_ids


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def group_mail_file_path(file_id: str, filename: str, mime_type: str) -> str:
    """邮件附件在收件成员 backend 工作区中的稳定路径（有扩展名则保留）。"""
    try:
        from backend.services.generation.agent.user_file_copy_service import (
            derive_file_extension,
        )
        ext = derive_file_extension(filename or "", mime_type or "")
    except Exception:  # noqa: BLE001 - 兜底：无扩展名
        ext = ""
    target = f"{GROUP_MAIL_FILE_DIR}/{file_id}"
    if ext:
        target += f".{ext}"
    return target


def _attachment_manifest(mail: group_chat_model.GroupMail) -> str:
    items = [a for a in (mail.attachments or []) if isinstance(a, dict)]
    if not items:
        return ""
    lines = ["### 附件（已写入你的工作区，可直接用 read 等工具打开）"]
    for a in items:
        if a.get("fileId"):
            filename = a.get("filename") or a["fileId"]
            mime = a.get("mimeType") or ""
            size = a.get("sizeBytes") or 0
            meta_parts = [p for p in (mime, _human_size(size) if size else "") if p]
            meta = f"（{'，'.join(meta_parts)}）" if meta_parts else ""
            target = group_mail_file_path(a["fileId"], filename, mime)
            lines.append(f"- {filename}{meta} -> {target}")
        elif a.get("path"):
            lines.append(f"- {a['path']}（附件读取失败，内容不可用）")
    return "\n".join(lines)


def _format_single_mail(mail: group_chat_model.GroupMail) -> str:
    recipients = "，".join(_recipient_names(mail))
    title = mail.title or ""
    manifest = _attachment_manifest(mail)
    body = (
        f"## {title}\n"
        f"### 发件人\n"
        f"{mail.senderAliasSnapshot}\n"
        f"### 本邮件发送的群成员列表\n"
        f"{recipients}\n"
        f"### 内容\n"
        f"{mail.content}"
    )
    if manifest:
        body = f"{body}\n\n{manifest}"
    return body


async def list_snapshot_mails(
    db: AsyncSession, task: group_chat_model.GroupTask
) -> List[group_chat_model.GroupMail]:
    """返回本轮冻结快照内的邮件实体（按 sequence 排序），供附件物化使用。"""
    receipt_ids = list(task.snapshotReceiptIds or [])
    if not receipt_ids:
        return []
    result = await db.execute(
        select(group_chat_model.GroupMail)
        .join(
            group_chat_model.GroupMailReceipt,
            group_chat_model.GroupMailReceipt.mailId == group_chat_model.GroupMail.id,
        )
        .filter(group_chat_model.GroupMailReceipt.id.in_(receipt_ids))
        .order_by(group_chat_model.GroupMail.sequence.asc())
    )
    return list(result.scalars().all())


async def materialize_mail_attachments(
    db: AsyncSession, chat_id: str, file_ids: Sequence[str]
) -> Dict[str, str]:
    """把邮件附件的中心库副本写入 chat 对应 backend 的工作区，供收件成员自行读取。

    - 不向该成员会话写入 File 子消息：文件只是"送到工作区"，由成员用 read 等工具自行打开。
    - best-effort：backend 构建或单个文件写入失败均不抛出，仅记录日志。
    返回 {fileId: 工作区路径}（仅含成功项）。
    """
    ordered = list(dict.fromkeys(
        f for f in (file_ids or []) if isinstance(f, str) and f
    ))
    if not ordered:
        return {}

    try:
        from backend.services.generation.agent.backend_factory import (
            build_backend_from_chat_id,
        )
        backend = await build_backend_from_chat_id(db, chat_id, thread_id=chat_id)
    except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
        logger.warning("[GroupMail] 构建收件成员 backend 失败 chat=%s: %s", chat_id, e)
        return {}

    from mambo_agents.backends.schemas import VirtualPath

    fs = FileService(db)
    paths: Dict[str, str] = {}
    for fid in ordered:
        try:
            db_file = await fs.get_file(fid)
            if db_file is None:
                continue
            raw = await fs.get_file_content(fid)
            target = group_mail_file_path(fid, db_file.filename, db_file.mime_type)
            results = await backend.aupload_files([(VirtualPath(target), raw)])
            if results and results[0].error is None:
                paths[fid] = target
        except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
            logger.warning(
                "[GroupMail] 附件写入收件成员工作区失败 file=%s chat=%s: %s",
                fid, chat_id, e,
            )
    return paths


async def read_mails(
    db: AsyncSession, task: group_chat_model.GroupTask
) -> str:
    """
    读取本轮冻结快照内的邮件文本。若无邮件返回明确的空提示。
    调用方负责在正常完成提交事务中确认已读。
    """
    receipt_ids = list(task.snapshotReceiptIds or [])
    if not receipt_ids:
        return "本轮没有未读邮件。"

    result = await db.execute(
        select(group_chat_model.GroupMail)
        .join(
            group_chat_model.GroupMailReceipt,
            group_chat_model.GroupMailReceipt.mailId == group_chat_model.GroupMail.id,
        )
        .filter(group_chat_model.GroupMailReceipt.id.in_(receipt_ids))
        .order_by(group_chat_model.GroupMail.sequence.asc())
    )
    mails = list(result.scalars().all())
    if not mails:
        return "本轮没有未读邮件。"
    return "\n\n".join(_format_single_mail(m) for m in mails)


# --- 通知合并 ---

async def _find_coalesced_notice(
    db: AsyncSession, group_id: str, recipient_chat_id: str
) -> Optional[group_chat_model.GroupTask]:
    key = f"{group_id}:{recipient_chat_id}"
    result = await db.execute(
        select(group_chat_model.GroupTask).filter(
            group_chat_model.GroupTask.coalesceKey == key
        )
    )
    return result.scalars().first()


async def ensure_notice_task(
    db: AsyncSession,
    group_state: group_chat_model.GroupState,
    recipient_chat_id: str,
    request_id: Optional[str] = None,
) -> group_chat_model.GroupTask:
    """
    为收件成员登记/复用 queued mail_notice。
    使用唯一 coalesceKey 合并“尚未运行”的同一成员通知。
    request_id 仅记录在新登记的任务上，用于用户群输入的幂等。
    """
    existing = await _find_coalesced_notice(db, group_state.groupId, recipient_chat_id)
    if existing is not None and existing.state == GroupTaskState.QUEUED.value:
        return existing

    seq = group_state.nextTaskSeq or 0
    group_state.nextTaskSeq = seq + 1

    task = group_chat_model.GroupTask(
        groupId=group_state.groupId,
        memberChatId=recipient_chat_id,
        sequence=seq,
        kind=GroupTaskKind.MAIL_NOTICE.value,
        state=GroupTaskState.QUEUED.value,
        requestId=request_id,
        coalesceKey=f"{group_state.groupId}:{recipient_chat_id}",
        payload={"prompt": "[system messages] 存在未读邮件"},
        mailReadRequested=False,
        attemptCount=0,
        createdAt=get_configured_now(),
    )
    db.add(task)
    await db.flush()
    return task


async def enqueue_mail_notice(
    db: AsyncSession,
    group_state: group_chat_model.GroupState,
    recipient_chat_id: str,
    receipt: group_chat_model.GroupMailReceipt,
    request_id: Optional[str] = None,
) -> group_chat_model.GroupTask:
    """
    为收件成员登记一个 queued mail_notice，并把该收件记录绑定到任务。
    """
    task = await ensure_notice_task(
        db, group_state, recipient_chat_id, request_id=request_id
    )
    receipt.notificationTaskId = task.id
    return task


# --- 正常结束提交 ---

async def commit_group_turn(
    db: AsyncSession,
    task: group_chat_model.GroupTask,
    group_state: group_chat_model.GroupState,
) -> List[Tuple[str, Optional[int]]]:
    """
    正常结束后的邮箱提交事务（幂等）。必须在调用前把 task 标记为 ready_to_commit。
    - 若 mailReadRequested，仅确认快照内未读记录为已读。
    - 提交本轮 staged 邮件，分配群 mail sequence，生成收件记录。
    - 合并收件成员的 queued mail_notice 并绑定 notificationTaskId。
    - task=succeeded，清理 activeTaskId，更新 version。
    """
    if task.state == GroupTaskState.SUCCEEDED.value:
        return []

    now = get_configured_now()

    # 保留成员 Master（= 用户本人）不执行生成，投递时不为其登记邮件通知任务
    master = await group_chat_crud.find_member_by_alias(db, group_state.groupId, MASTER_ALIAS)
    master_chat_id = master.id if master else None

    # 1. 确认已读（仅快照内）
    if task.mailReadRequested:
        receipt_ids = list(task.snapshotReceiptIds or [])
        if receipt_ids:
            result = await db.execute(
                select(group_chat_model.GroupMailReceipt).filter(
                    group_chat_model.GroupMailReceipt.id.in_(receipt_ids),
                    group_chat_model.GroupMailReceipt.readAt.is_(None),
                )
            )
            for receipt in result.scalars().all():
                receipt.readAt = now
                receipt.readByTaskId = task.id

    # 2. 提交待投递邮件：本轮暂存的 + 该发件人此前“已同意但同批存在拒绝而暂缓”的（deferred）
    result = await db.execute(
        select(group_chat_model.GroupMail)
        .filter(
            group_chat_model.GroupMail.groupId == group_state.groupId,
            or_(
                and_(
                    group_chat_model.GroupMail.sourceTaskId == task.id,
                    group_chat_model.GroupMail.state == GroupMailState.STAGED.value,
                ),
                and_(
                    group_chat_model.GroupMail.senderChatId == task.memberChatId,
                    group_chat_model.GroupMail.state == GroupMailState.DEFERRED.value,
                ),
            ),
        )
        .order_by(
            group_chat_model.GroupMail.createdAt.asc(),
            group_chat_model.GroupMail.toolCallOrder.asc(),
        )
    )
    staged_mails = list(result.scalars().all())

    sent: List[Tuple[str, Optional[int]]] = []
    for mail in staged_mails:
        seq = group_state.nextMailSeq or 0
        group_state.nextMailSeq = seq + 1
        mail.state = GroupMailState.SENT.value
        mail.sequence = seq
        mail.sentAt = now
        await db.flush()
        sent.append((mail.id, seq))

        for item in (mail.recipientSnapshot or []):
            recipient_chat_id = item.get("memberChatId")
            if not recipient_chat_id:
                continue
            receipt = group_chat_model.GroupMailReceipt(
                mailId=mail.id,
                recipientChatId=recipient_chat_id,
                createdAt=now,
            )
            db.add(receipt)
            await db.flush()
            if recipient_chat_id != master_chat_id:
                await enqueue_mail_notice(db, group_state, recipient_chat_id, receipt)

    # 3. 结束轮次
    task.state = GroupTaskState.SUCCEEDED.value
    task.finishedAt = now
    if group_state.activeTaskId == task.id:
        group_state.activeTaskId = None
    group_state.version = (group_state.version or 0) + 1
    group_state.updatedAt = now

    await db.commit()
    return sent


# ──────────────────────────────────────────────
# 审核模式（mail_review）
# ──────────────────────────────────────────────

class ReviewOutcome:
    """审核批次定稿结果。pending>0 表示该批仍有邮件待用户审核。"""

    def __init__(
        self,
        pending: int = 0,
        finalized: bool = False,
        delivered: Optional[List[Tuple[str, Optional[int]]]] = None,
        decision_text: Optional[str] = None,
        sender_chat_id: Optional[str] = None,
    ) -> None:
        self.pending = pending
        self.finalized = finalized
        self.delivered = delivered or []
        self.decision_text = decision_text
        self.sender_chat_id = sender_chat_id


async def _task_mails(
    db: AsyncSession, task_id: str, states: Sequence[str]
) -> List[group_chat_model.GroupMail]:
    result = await db.execute(
        select(group_chat_model.GroupMail)
        .filter(
            group_chat_model.GroupMail.sourceTaskId == task_id,
            group_chat_model.GroupMail.state.in_(list(states)),
        )
        .order_by(group_chat_model.GroupMail.toolCallOrder.asc())
    )
    return list(result.scalars().all())


async def hold_for_review(
    db: AsyncSession,
    task: group_chat_model.GroupTask,
    group_state: group_chat_model.GroupState,
) -> int:
    """
    审核模式：轮次正常结束后不投递，把本轮 staged 邮件转入 reviewing，并暂停整群等待用户逐封审核。
    该轮任务停在 ready_to_commit（邮件提交尚未完成），activeTaskId 保留；期间不触发任何收件成员。
    既无 staged 也无 reviewing 邮件时（含重启恢复场景）按正常结束处理。
    返回进入待审核的邮件数。
    """
    now = get_configured_now()
    staged = await _task_mails(db, task.id, [GroupMailState.STAGED.value])
    reviewing = await _task_mails(db, task.id, [GroupMailState.REVIEWING.value])
    if not staged and not reviewing:
        await commit_group_turn(db, task, group_state)
        return 0

    for mail in staged:
        mail.state = GroupMailState.REVIEWING.value

    task.state = GroupTaskState.READY_TO_COMMIT.value
    task.finishedAt = now
    group_state.status = GroupStatus.PAUSED.value
    group_state.pauseReason = GroupPauseReason.MAIL_REVIEW.value
    group_state.version = (group_state.version or 0) + 1
    group_state.updatedAt = now
    await db.commit()
    return len(staged) + len(reviewing)


async def list_review_queue(
    db: AsyncSession, group_id: str, decided_limit: int = 50
) -> Tuple[List[group_chat_model.GroupMail], List[group_chat_model.GroupMail]]:
    """返回 (待审核邮件, 已决策邮件)。已决策含 rejected（被拒）与 deferred（已同意、待下一轮一并投递）。"""
    pending_result = await db.execute(
        select(group_chat_model.GroupMail)
        .filter(
            group_chat_model.GroupMail.groupId == group_id,
            group_chat_model.GroupMail.state == GroupMailState.REVIEWING.value,
        )
        .order_by(group_chat_model.GroupMail.createdAt.asc())
    )
    decided_result = await db.execute(
        select(group_chat_model.GroupMail)
        .filter(
            group_chat_model.GroupMail.groupId == group_id,
            group_chat_model.GroupMail.state.in_(
                [GroupMailState.REJECTED.value, GroupMailState.DEFERRED.value]
            ),
        )
        .order_by(group_chat_model.GroupMail.createdAt.desc())
        .limit(decided_limit)
    )
    return list(pending_result.scalars().all()), list(decided_result.scalars().all())


async def get_group_mail(
    db: AsyncSession, group_id: str, mail_id: str
) -> group_chat_model.GroupMail:
    result = await db.execute(
        select(group_chat_model.GroupMail).filter(
            group_chat_model.GroupMail.id == mail_id,
            group_chat_model.GroupMail.groupId == group_id,
        )
    )
    mail = result.scalars().first()
    if mail is None:
        raise _bad(MailErrorCode.MAIL_NOT_FOUND, "mail_not_found", 404)
    return mail


def _mail_label(mail: group_chat_model.GroupMail) -> str:
    title = (mail.title or "").strip()
    return f"「{title}」" if title else "（无标题邮件）"


def build_review_decision_message(
    rejected: Sequence[group_chat_model.GroupMail],
    agreed: Sequence[group_chat_model.GroupMail],
) -> str:
    """
    把审批结果整理成注入发信人子会话的 user message。
    例：[system messages] 用户拒绝「方案A」原因：论据不足；用户同意「方案B」-> 已加入本轮待发箱，将在本轮正常结束后投递。
    """
    parts: List[str] = []
    for mail in rejected:
        reason = (mail.rejectReason or "").strip() or "未说明"
        parts.append(f"用户拒绝{_mail_label(mail)}原因：{reason}")
    if agreed:
        labels = "、".join(_mail_label(m) for m in agreed)
        parts.append(f"用户同意{labels}-> 已加入本轮待发箱，将在本轮正常结束后投递。")
    return "[system messages] " + "；".join(parts)


async def approve_mail(db: AsyncSession, group_id: str, mail_id: str) -> ReviewOutcome:
    """用户同意投递：reviewing -> staged（回到待投递）。"""
    mail = await get_group_mail(db, group_id, mail_id)
    if mail.state != GroupMailState.REVIEWING.value:
        raise _bad(MailErrorCode.INVALID_STATE, "mail_not_reviewing", 409)
    mail.state = GroupMailState.STAGED.value
    mail.reviewedAt = get_configured_now()
    await db.flush()
    return await _maybe_finalize_review(db, group_id, mail.sourceTaskId)


async def reject_mail(
    db: AsyncSession, group_id: str, mail_id: str, reason: str
) -> ReviewOutcome:
    """用户拒绝投递：reviewing -> rejected，记录必填的拒绝原因。"""
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise _bad(MailErrorCode.REJECT_REASON_REQUIRED, "reject_reason_required", 400)
    mail = await get_group_mail(db, group_id, mail_id)
    if mail.state != GroupMailState.REVIEWING.value:
        raise _bad(MailErrorCode.INVALID_STATE, "mail_not_reviewing", 409)
    mail.state = GroupMailState.REJECTED.value
    mail.rejectReason = clean_reason
    mail.reviewedAt = get_configured_now()
    await db.flush()
    return await _maybe_finalize_review(db, group_id, mail.sourceTaskId)


async def _maybe_finalize_review(
    db: AsyncSession, group_id: str, task_id: str
) -> ReviewOutcome:
    """
    同一批（同一次轮次产生的邮件）全部审批完成后定稿：
    - 无拒绝：立即按正常结束提交投递（与自动模式一致），并顺带投递该发件人此前 deferred 的邮件。
    - 存在拒绝：同意的邮件转 deferred（本轮不投递、不触发收件人），本轮结束；
      返回需要注入发信人的「拒绝/同意」结果消息，用于触发发信人再生成一次。
    """
    task = await group_chat_crud.get_task(db, task_id)
    state = await group_chat_crud.get_group_state(db, group_id)
    if task is None or state is None:
        raise _bad(MailErrorCode.MAIL_NOT_FOUND, "group_task_not_found", 404)

    remaining = await _task_mails(db, task.id, [GroupMailState.REVIEWING.value])
    if remaining:
        # 本批尚未审完：仅持久化本次单封决策（同意/拒绝），不触发任何后续流程。
        # 必须提交，否则请求结束时会话回滚，导致决策丢失、同批永远无法定稿。
        await db.commit()
        return ReviewOutcome(pending=len(remaining))

    now = get_configured_now()
    rejected = await _task_mails(db, task.id, [GroupMailState.REJECTED.value])
    agreed = await _task_mails(db, task.id, [GroupMailState.STAGED.value])

    if rejected:
        for mail in agreed:
            mail.state = GroupMailState.DEFERRED.value
        task.state = GroupTaskState.SUCCEEDED.value
        task.finishedAt = now
        if state.activeTaskId == task.id:
            state.activeTaskId = None
        state.status = GroupStatus.READY.value
        state.pauseReason = None
        state.version = (state.version or 0) + 1
        state.updatedAt = now
        await db.commit()
        return ReviewOutcome(
            finalized=True,
            decision_text=build_review_decision_message(rejected, agreed),
            sender_chat_id=task.memberChatId,
        )

    # 全部同意
    state.status = GroupStatus.READY.value
    state.pauseReason = None
    delivered = await commit_group_turn(db, task, state)
    return ReviewOutcome(
        finalized=True, delivered=delivered, sender_chat_id=task.memberChatId
    )
