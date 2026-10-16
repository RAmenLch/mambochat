# backend/services/group_chat/service.py

"""
群组会话服务：原子建群、群详情、生命周期删除、成员与结构校验。

本模块只负责群组这一业务实体的结构完整性，不承担邮件调度与生成桥接
（见 mail_service / scheduler / generation_bridge）。
"""

import logging
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.models import chat_model, agent_model, group_chat_model
from backend.crud import group_chat_crud, message_crud, setting_crud
from backend.models.base_model import generate_uuid
from backend.schemas.enums import (
    FolderType, GroupMailMode, GroupMailState, GroupStatus, GroupPauseReason, GroupTaskKind,
    GroupTaskState, AgentItemType, MessageStatus, SubMessageType,
)
from backend.schemas.group_chat import (
    GroupChatCreate, GroupSettingsUpdate, normalize_member_alias,
    MEMBER_ALIAS_MAX_LEN, MASTER_ALIAS, MASTER_SORT_ORDER,
)
from backend.exceptions import AppHTTPException
from backend.config.timezone_config import get_configured_now
from backend.services.group_chat import events, generation_bridge, mail_service

logger = logging.getLogger(__name__)

MIN_GROUP_MEMBERS = 3


class GroupErrorCode:
    NOT_FOUND = "GROUP_NOT_FOUND"
    MEMBER_COUNT_INVALID = "GROUP_MEMBER_COUNT_INVALID"
    ALIAS_DUPLICATE = "GROUP_ALIAS_DUPLICATE"
    ALIAS_INVALID = "GROUP_ALIAS_INVALID"
    ALIAS_RESERVED = "GROUP_ALIAS_RESERVED"
    AGENT_NOT_FOUND = "GROUP_AGENT_NOT_FOUND"
    PARENT_INVALID = "GROUP_PARENT_INVALID"
    STRUCTURE_INVALID = "GROUP_STRUCTURE_INVALID"
    FORBIDDEN_OPERATION = "GROUP_FORBIDDEN_OPERATION"


def _bad(code: str, detail: str, status: int = 400) -> AppHTTPException:
    return AppHTTPException(status_code=status, error_code=code, detail=detail)


async def is_group(db: AsyncSession, chat_id: str) -> bool:
    """判断给定 Chat 是否为群父节点。"""
    result = await db.execute(
        select(chat_model.Chat.id).filter(
            chat_model.Chat.id == chat_id,
            chat_model.Chat.itemType == "folder",
            chat_model.Chat.folderType == FolderType.GROUP.value,
        )
    )
    return result.scalar() is not None


async def resolve_group_id_for_member(db: AsyncSession, chat_id: str) -> Optional[str]:
    """
    若 chat_id 是某群成员子会话，返回其所属 groupId；否则返回 None。
    群外普通会话返回 None。
    """
    chat = await db.get(chat_model.Chat, chat_id)
    if not chat or not chat.parentId or not chat.memberAlias:
        return None
    if await is_group(db, chat.parentId):
        return chat.parentId
    return None


async def _next_sort_order(db: AsyncSession, parent_id: Optional[str]) -> int:
    stmt = select(func.max(chat_model.Chat.sortOrder)).filter(
        chat_model.Chat.parentId == parent_id
    )
    result = await db.execute(stmt)
    max_order = result.scalar()
    return (max_order if max_order is not None else -1) + 1


def is_master_member(chat: Optional[chat_model.Chat]) -> bool:
    """判断成员是否为保留的用户成员 Master。"""
    return bool(chat is not None and chat.memberAlias == MASTER_ALIAS)


async def ensure_master_member(
    db: AsyncSession, group_id: str
) -> Tuple[chat_model.Chat, bool]:
    """
    确保群内存在保留成员 Master（= 用户本人），不存在则补建。
    返回 (Master 成员节点, 是否本次新建)。只 flush，不 commit，事务由调用方持有。
    """
    existing = await group_chat_crud.find_member_by_alias(db, group_id, MASTER_ALIAS)
    if existing is not None:
        return existing, False
    node = chat_model.Chat(
        name=MASTER_ALIAS,
        itemType="chat",
        chatMode="agent",
        agentId=None,
        parentId=group_id,
        memberAlias=MASTER_ALIAS,
        sortOrder=MASTER_SORT_ORDER,
    )
    db.add(node)
    await db.flush()
    return node, True


async def _validate_parent(db: AsyncSession, parent_id: Optional[str]) -> Optional[str]:
    """校验群组父节点位置；返回规范化后的 parentId（None 表示根目录）。"""
    if parent_id in (None, "", "root"):
        return None
    parent = await db.get(chat_model.Chat, parent_id)
    if not parent:
        raise _bad(GroupErrorCode.PARENT_INVALID, "parent_not_found", 404)
    if parent.itemType != "folder":
        raise _bad(GroupErrorCode.PARENT_INVALID, "parent_not_folder")
    if parent.folderType == FolderType.GROUP.value:
        # 禁止群组嵌套群组
        raise _bad(GroupErrorCode.PARENT_INVALID, "nested_group_forbidden")
    return parent_id


async def create_group_chat(
    db: AsyncSession, payload: GroupChatCreate
) -> schemas.GroupCreatedResponse:
    """
    原子创建群父节点、GroupState 和 N 个成员子会话。
    任一成员创建失败时整体回滚，不残留父文件夹、状态或子会话。
    """
    members = payload.members
    if len(members) < MIN_GROUP_MEMBERS:
        raise _bad(
            GroupErrorCode.MEMBER_COUNT_INVALID,
            f"group requires at least {MIN_GROUP_MEMBERS} members",
        )

    # 别名规范化冗余校验 + 群内唯一（区分大小写）
    normalized_aliases: List[str] = []
    seen = set()
    for m in members:
        try:
            alias = normalize_member_alias(m.memberAlias)
        except ValueError as e:
            raise _bad(GroupErrorCode.ALIAS_INVALID, str(e))
        if alias in seen:
            raise _bad(GroupErrorCode.ALIAS_DUPLICATE, f"duplicate alias: {alias}")
        if alias == MASTER_ALIAS:
            raise _bad(GroupErrorCode.ALIAS_RESERVED, f"reserved alias: {MASTER_ALIAS}")
        seen.add(alias)
        normalized_aliases.append(alias)
    # 保留别名先占位，避免与自动追加的 Master 成员冲突
    seen.add(MASTER_ALIAS)

    parent_id = await _validate_parent(db, payload.parentId)

    # 校验 Agent 可用性（允许重复）
    agent_ids = {m.agentId for m in members}
    agent_names: Dict[str, str] = {}
    for agent_id in agent_ids:
        agent = await db.get(agent_model.Agent, agent_id)
        if not agent or agent.itemType != AgentItemType.AGENT.value:
            raise _bad(
                GroupErrorCode.AGENT_NOT_FOUND,
                f"agent not available: {agent_id}",
                404,
            )
        agent_names[agent_id] = agent.name

    try:
        group_sort_order = await _next_sort_order(db, parent_id)
        group_node = chat_model.Chat(
            name=payload.name,
            itemType="folder",
            folderType=FolderType.GROUP.value,
            parentId=parent_id,
            sortOrder=group_sort_order,
        )
        db.add(group_node)
        await db.flush()

        state = group_chat_model.GroupState(
            groupId=group_node.id,
            status=GroupStatus.READY.value,
            autoRoundLimit=payload.autoRoundLimit,
            autoRoundCount=0,
            mailMode=payload.mailMode.value,
            nextTaskSeq=0,
            nextMailSeq=0,
            version=0,
        )
        db.add(state)

        member_nodes: List[chat_model.Chat] = []
        # 保留成员 Master（= 用户本人），无 Agent、不参与生成调度
        master_node = chat_model.Chat(
            name=MASTER_ALIAS,
            itemType="chat",
            chatMode="agent",
            agentId=None,
            parentId=group_node.id,
            memberAlias=MASTER_ALIAS,
            sortOrder=MASTER_SORT_ORDER,
        )
        db.add(master_node)
        member_nodes.append(master_node)
        for index, member in enumerate(members):
            alias = normalized_aliases[index]
            member_node = chat_model.Chat(
                name=alias,
                itemType="chat",
                chatMode="agent",
                agentId=member.agentId,
                parentId=group_node.id,
                memberAlias=alias,
                sortOrder=index,
            )
            db.add(member_node)
            member_nodes.append(member_node)

        await db.flush()

        detail = _build_detail(
            group_node=group_node,
            state=state,
            member_nodes=member_nodes,
            agent_names=agent_names,
            unread_map={},
            queued_map={},
        )

        await db.commit()
        return detail
    except AppHTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("创建群组失败")
        raise _bad(GroupErrorCode.STRUCTURE_INVALID, "group_creation_failed", 500)


async def _total_auto_rounds(db: AsyncSession, group_id: str) -> int:
    """群累计实际启动过的自动邮件轮次（跨额度周期，仅用于展示）。"""
    result = await db.execute(
        select(func.count(group_chat_model.GroupTask.id)).filter(
            group_chat_model.GroupTask.groupId == group_id,
            group_chat_model.GroupTask.kind == GroupTaskKind.MAIL_NOTICE.value,
            group_chat_model.GroupTask.startedAt.is_not(None),
        )
    )
    return int(result.scalar() or 0)


def _build_detail(
    group_node: chat_model.Chat,
    state: group_chat_model.GroupState,
    member_nodes: List[chat_model.Chat],
    agent_names: Dict[str, str],
    unread_map: Dict[str, int],
    queued_map: Dict[str, int],
    total_auto_rounds: int = 0,
) -> schemas.GroupCreatedResponse:
    members = []
    for m in member_nodes:
        is_user = m.memberAlias == MASTER_ALIAS
        members.append(
            schemas.GroupMemberResponse(
                chatId=m.id,
                memberAlias=m.memberAlias,
                agentId=m.agentId,
                agentName=agent_names.get(m.agentId) if m.agentId else None,
                name=m.name,
                sortOrder=m.sortOrder,
                # 用户成员不参与生成调度，未读/排队对自身无意义，恒为 0
                unreadCount=0 if is_user else unread_map.get(m.id, 0),
                pendingCount=0 if is_user else queued_map.get(m.id, 0),
                isUser=is_user,
            )
        )
    total_unread = sum(mm.unreadCount for mm in members)
    total_queued = sum(mm.pendingCount for mm in members)
    return schemas.GroupCreatedResponse(
        groupId=group_node.id,
        name=group_node.name,
        parentId=group_node.parentId,
        status=GroupStatus(state.status),
        pauseReason=state.pauseReason,
        autoRoundLimit=state.autoRoundLimit,
        autoRoundCount=state.autoRoundCount,
        mailMode=GroupMailMode(state.mailMode or GroupMailMode.AUTO.value),
        totalAutoRoundCount=total_auto_rounds,
        version=state.version,
        activeTaskId=state.activeTaskId,
        members=members,
        unreadCount=total_unread,
        queuedCount=total_queued,
    )


async def _unread_counts(db: AsyncSession, group_id: str) -> Dict[str, int]:
    """统计每个成员的未读邮件数。"""
    result = await db.execute(
        select(
            group_chat_model.GroupMailReceipt.recipientChatId,
            func.count(group_chat_model.GroupMailReceipt.id),
        )
        .join(
            group_chat_model.GroupMail,
            group_chat_model.GroupMail.id == group_chat_model.GroupMailReceipt.mailId,
        )
        .filter(
            group_chat_model.GroupMail.groupId == group_id,
            group_chat_model.GroupMail.state == GroupMailState.SENT.value,
            group_chat_model.GroupMailReceipt.readAt.is_(None),
        )
        .group_by(group_chat_model.GroupMailReceipt.recipientChatId)
    )
    return {row[0]: row[1] for row in result.all()}


async def _queued_counts(db: AsyncSession, group_id: str) -> Dict[str, int]:
    """统计每个成员排队中的任务数。"""
    result = await db.execute(
        select(
            group_chat_model.GroupTask.memberChatId,
            func.count(group_chat_model.GroupTask.id),
        )
        .filter(
            group_chat_model.GroupTask.groupId == group_id,
            group_chat_model.GroupTask.state.in_(
                [
                    GroupTaskState.QUEUED.value,
                    GroupTaskState.RUNNING.value,
                    GroupTaskState.WAITING_REVIEW.value,
                    GroupTaskState.WAITING_USER.value,
                ]
            ),
        )
        .group_by(group_chat_model.GroupTask.memberChatId)
    )
    return {row[0]: row[1] for row in result.all()}


async def get_group_detail(db: AsyncSession, group_id: str) -> schemas.GroupDetailResponse:
    group_node = await group_chat_crud.get_group_chat(db, group_id)
    if not group_node:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.STRUCTURE_INVALID, "group_state_missing", 500)

    # 确保保留成员 Master（= 用户本人）存在；存量群按需补建（不强制迁移）
    _, master_created = await ensure_master_member(db, group_id)
    if master_created:
        await db.commit()

    member_nodes = await group_chat_crud.list_member_chats(db, group_id)

    agent_names: Dict[str, str] = {}
    agent_ids = {m.agentId for m in member_nodes if m.agentId}
    if agent_ids:
        result = await db.execute(
            select(agent_model.Agent.id, agent_model.Agent.name).filter(
                agent_model.Agent.id.in_(agent_ids)
            )
        )
        agent_names = {row[0]: row[1] for row in result.all()}

    unread_map = await _unread_counts(db, group_id)
    queued_map = await _queued_counts(db, group_id)
    total_auto_rounds = await _total_auto_rounds(db, group_id)
    return _build_detail(
        group_node, state, member_nodes, agent_names, unread_map, queued_map, total_auto_rounds
    )


async def _copy_member_messages(
    db: AsyncSession,
    src_chat_id: str,
    dst_chat_id: str,
    cutoff_time,
    extend_broadcast: bool = False,
) -> None:
    """
    把成员子会话的活跃路径消息复制到新会话，只保留截点之前的前缀。
    - extend_broadcast=False：保留 createdAt <= 截点 的消息（该成员未收到这条邮件）。
    - extend_broadcast=True（该成员是所点邮件的收件成员）：该邮件"已送达但尚未被该成员回复"，
      保留到"截点之后第一条 assistant 消息"之前，即含其收到的用户消息
      （用户来信对应广播正文；成员回信对应"存在未读邮件"通知），但不含其对它的回复。
    复用普通会话复制的清洗规则：丢弃 VERSION_SNAPSHOT、中间态置 FAILED、补回 TaskSubStep。
    """
    active_messages = await message_crud.get_messages_by_chat(db, chat_id=src_chat_id)
    if not active_messages:
        return

    # 需要扩展时：定位"截点之后第一条 assistant 消息"作为上界（保留其之前的消息）
    boundary = None
    if extend_broadcast:
        for msg in active_messages:
            if (
                msg.role == "assistant"
                and msg.createdAt is not None
                and msg.createdAt > cutoff_time
            ):
                boundary = msg.createdAt
                break

    # 保留判定应形成路径前缀：遇到第一个越界的消息即停止
    kept = []
    for msg in active_messages:
        if extend_broadcast:
            if boundary is not None and msg.createdAt is not None and msg.createdAt >= boundary:
                break
            kept.append(msg)
        else:
            if msg.createdAt is not None and msg.createdAt <= cutoff_time:
                kept.append(msg)
            else:
                break
    if not kept:
        return

    task_subs = await message_crud.get_task_substeps_by_message_ids(db, [m.id for m in kept])
    task_subs_by_msg: Dict[str, List] = {}
    for sub in task_subs:
        task_subs_by_msg.setdefault(sub.messageId, []).append(sub)

    last_new_msg_id = None
    for msg in kept:
        new_msg = chat_model.Message(
            role=msg.role,
            sortOrder=msg.sortOrder,
            chatId=dst_chat_id,
            parentId=last_new_msg_id,
            lastActiveAt=msg.lastActiveAt,
            createdAt=msg.createdAt,
        )
        db.add(new_msg)
        await db.flush()
        last_new_msg_id = new_msg.id

        new_sub_messages = []
        merged_subs = list(msg.sub_messages) + task_subs_by_msg.get(msg.id, [])
        merged_subs.sort(key=lambda s: (s.sortOrder, s.createdAt))
        for sub in merged_subs:
            if sub.type == SubMessageType.VERSION_SNAPSHOT.value:
                continue
            safe_status = sub.status
            if safe_status in (
                MessageStatus.GENERATING.value,
                MessageStatus.PENDING_REVIEW.value,
            ):
                safe_status = MessageStatus.FAILED.value
            new_sub_messages.append(
                chat_model.SubMessage(
                    content=sub.content,
                    sortOrder=sub.sortOrder,
                    type=sub.type,
                    config=sub.config,
                    status=safe_status,
                    messageId=new_msg.id,
                    createdAt=sub.createdAt,
                )
            )
        db.add_all(new_sub_messages)
    await db.flush()


async def duplicate_group_chat(
    db: AsyncSession, group_id: str, up_to_mail_id: str
) -> schemas.GroupCreatedResponse:
    """
    复制群组到指定邮件为止，生成一个干净的新群副本。

    - 粒度=轮次：点中某封邮件即选中它所属的整轮；邮件流复制到该轮结束。
    - 子会话按"时间截点"截取：以目标邮件投递时刻为准，保留在此之前产生的消息。
      时间戳在副本里原样保留，故副本的副本也能继续复制（不依赖已被丢弃的 GroupTask）。
    - 已读状态按截点重建：读取时间晚于截点的收件记录置回未读。
    - 群非空闲（存在活动轮次）时拒绝。
    """
    group_node = await group_chat_crud.get_group_chat(db, group_id)
    if not group_node:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)

    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.STRUCTURE_INVALID, "group_state_missing", 500)
    if state.status == GroupStatus.DELETING.value:
        raise _bad(GroupErrorCode.FORBIDDEN_OPERATION, "group_deleting", 409)
    # 非空闲：有正在执行 / 等待人工的轮次时禁止复制，避免快照落在半截
    if state.activeTaskId:
        raise _bad(GroupErrorCode.FORBIDDEN_OPERATION, "group_busy", 409)

    target_mail = await group_chat_crud.get_mail(db, up_to_mail_id)
    if (
        not target_mail
        or target_mail.groupId != group_id
        or target_mail.state != GroupMailState.SENT.value
    ):
        raise _bad(GroupErrorCode.STRUCTURE_INVALID, "mail_not_found_or_not_sent", 404)

    # ── 1. 定位截点 ──
    # 统一按时间截取：以目标邮件投递时刻为截点。不必依赖 GroupTask，
    # 时间戳在副本里原样保留，因此"副本的副本"也能继续复制。
    cutoff_time = target_mail.sentAt or target_mail.createdAt
    # 所点邮件的收件成员（副本里该快照同样保留，故也支持"副本的副本"）
    recipient_ids = {
        item.get("memberChatId")
        for item in (target_mail.recipientSnapshot or [])
        if item.get("memberChatId")
    }
    # 整轮：邮件流上界取该邮件所属轮次的最后一封（同 sourceTaskId 的最大 sequence）。
    # Master 来信每封自成一轮，此查询即返回它自己。
    upper_res = await db.execute(
        select(func.max(group_chat_model.GroupMail.sequence)).filter(
            group_chat_model.GroupMail.groupId == group_id,
            group_chat_model.GroupMail.sourceTaskId == target_mail.sourceTaskId,
            group_chat_model.GroupMail.state == GroupMailState.SENT.value,
        )
    )
    mail_upper_seq = upper_res.scalar_one_or_none()
    if mail_upper_seq is None:
        mail_upper_seq = target_mail.sequence

    # ── 2. 复制群父节点、状态与成员 ──
    lang_setting = await setting_crud.get_setting(db, "language")
    language = lang_setting.value if lang_setting else "zh-CN"
    copy_suffix = "副本" if language == "zh-CN" else "Copy"

    parent_id = group_node.parentId
    new_group_node = chat_model.Chat(
        name=f"{group_node.name} ({copy_suffix})",
        itemType="folder",
        folderType=FolderType.GROUP.value,
        parentId=parent_id,
        sortOrder=await _next_sort_order(db, parent_id),
    )
    db.add(new_group_node)
    await db.flush()

    new_state = group_chat_model.GroupState(
        groupId=new_group_node.id,
        status=GroupStatus.READY.value,
        autoRoundLimit=state.autoRoundLimit,
        autoRoundCount=0,
        mailMode=state.mailMode,
        nextTaskSeq=0,
        nextMailSeq=0,
        version=0,
    )
    db.add(new_state)

    old_members = await group_chat_crud.list_member_chats(db, group_id)
    member_id_map: Dict[str, str] = {}
    for m in old_members:
        new_member = chat_model.Chat(
            name=m.name,
            itemType="chat",
            chatMode=m.chatMode,
            agentId=m.agentId,
            parentId=new_group_node.id,
            memberAlias=m.memberAlias,
            sortOrder=m.sortOrder,
        )
        db.add(new_member)
        await db.flush()
        member_id_map[m.id] = new_member.id

    # ── 3. 复制邮件（至轮末）与收件记录（已读按截点重建） ──
    mail_list: List[group_chat_model.GroupMail] = []
    if mail_upper_seq is not None:
        mail_res = await db.execute(
            select(group_chat_model.GroupMail)
            .filter(
                group_chat_model.GroupMail.groupId == group_id,
                group_chat_model.GroupMail.state == GroupMailState.SENT.value,
                group_chat_model.GroupMail.sequence <= mail_upper_seq,
            )
            .order_by(group_chat_model.GroupMail.sequence.asc())
        )
        mail_list = list(mail_res.scalars().all())

    receipts_by_mail: Dict[str, List[group_chat_model.GroupMailReceipt]] = {}
    if mail_list:
        receipt_res = await db.execute(
            select(group_chat_model.GroupMailReceipt).filter(
                group_chat_model.GroupMailReceipt.mailId.in_([m.id for m in mail_list])
            )
        )
        for r in receipt_res.scalars().all():
            receipts_by_mail.setdefault(r.mailId, []).append(r)

    # 保持同轮邮件在副本里仍属同一"轮"（用合成 id 映射源 sourceTaskId），
    # 既避免与源邮件 (sourceTaskId, toolCallId) 唯一约束冲突，又保留前端按轮分组的展示。
    source_task_id_map: Dict[str, str] = {}

    def _new_source_task_id(old_id: str) -> str:
        if old_id not in source_task_id_map:
            source_task_id_map[old_id] = generate_uuid()
        return source_task_id_map[old_id]

    new_seq = 0
    for mail in mail_list:
        new_mail = group_chat_model.GroupMail(
            groupId=new_group_node.id,
            sourceTaskId=_new_source_task_id(mail.sourceTaskId),
            senderChatId=member_id_map.get(mail.senderChatId, mail.senderChatId),
            senderAliasSnapshot=mail.senderAliasSnapshot,
            recipientSnapshot=[
                {
                    "memberChatId": member_id_map.get(
                        item.get("memberChatId"), item.get("memberChatId")
                    ),
                    "memberName": item.get("memberName"),
                }
                for item in (mail.recipientSnapshot or [])
            ],
            title=mail.title,
            content=mail.content,
            attachments=mail.attachments,
            toolCallId=mail.toolCallId,
            toolCallOrder=mail.toolCallOrder,
            state=GroupMailState.SENT.value,
            sequence=new_seq,
            createdAt=mail.createdAt,
            sentAt=mail.sentAt,
        )
        db.add(new_mail)
        await db.flush()
        new_seq += 1

        for r in receipts_by_mail.get(mail.id, []):
            new_recipient = member_id_map.get(r.recipientChatId)
            if new_recipient is None:
                continue
            # 读取时间晚于截点（即截点之后才读的）置回未读
            keep_read = r.readAt is not None and r.readAt <= cutoff_time
            db.add(
                group_chat_model.GroupMailReceipt(
                    mailId=new_mail.id,
                    recipientChatId=new_recipient,
                    readAt=r.readAt if keep_read else None,
                    createdAt=r.createdAt,
                )
            )

    new_state.nextMailSeq = new_seq
    await db.flush()

    # ── 4. 复制各成员子会话消息（截取到截点） ──
    # 所点邮件的收件成员：额外保留其"已送达"的用户消息（用户来信=广播正文；成员回信="存在未读邮件"通知），
    # 但不保留其回复；非收件成员按截点前保留。
    for old_member in old_members:
        extend = old_member.id in recipient_ids
        await _copy_member_messages(
            db, old_member.id, member_id_map[old_member.id], cutoff_time, extend
        )

    await db.commit()
    return await get_group_detail(db, new_group_node.id)


async def update_group_settings(
    db: AsyncSession, group_id: str, payload: GroupSettingsUpdate
) -> schemas.GroupControlResponse:
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)

    if payload.autoRoundLimit is not None:
        state.autoRoundLimit = payload.autoRoundLimit
    if payload.mailMode is not None:
        # 只影响之后的轮次：当前若已有待审核批次，仍由用户逐封决定
        state.mailMode = payload.mailMode.value
    if payload.resetAutoRoundCount:
        state.autoRoundCount = 0
        # 因达到轮次上限而暂停的群：重置即为继续执行，同步解除该暂停
        if state.pauseReason == GroupPauseReason.ROUND_LIMIT.value:
            state.status = GroupStatus.READY.value
            state.pauseReason = None
    state.version = (state.version or 0) + 1
    state.updatedAt = get_configured_now()
    await db.commit()
    return schemas.GroupControlResponse(
        groupId=group_id, status=GroupStatus(state.status), version=state.version
    )


async def pause_group(db: AsyncSession, group_id: str) -> schemas.GroupControlResponse:
    """暂停后续调度，不等同取消当前生成。"""
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)
    state.status = GroupStatus.PAUSED.value
    state.pauseReason = GroupPauseReason.MANUAL.value
    state.version = (state.version or 0) + 1
    state.updatedAt = get_configured_now()
    await db.commit()
    return schemas.GroupControlResponse(
        groupId=group_id, status=GroupStatus(state.status), version=state.version
    )


async def resume_group(db: AsyncSession, group_id: str) -> schemas.GroupControlResponse:
    """恢复可继续群；待审核/失败不能被普通 resume 越过。"""
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)
    if state.pauseReason in (
        GroupPauseReason.REVIEW.value,
        GroupPauseReason.ASK_USER.value,
    ):
        raise _bad(
            "GROUP_RESUME_BLOCKED",
            "cannot_resume_waiting_review_or_user",
            409,
        )
    if state.status == GroupStatus.DELETING.value:
        raise _bad("GROUP_RESUME_BLOCKED", "group_deleting", 409)
    state.status = GroupStatus.READY.value
    state.pauseReason = None
    state.version = (state.version or 0) + 1
    state.updatedAt = get_configured_now()
    await db.commit()
    return schemas.GroupControlResponse(
        groupId=group_id, status=GroupStatus(state.status), version=state.version
    )


async def validate_group_structure(db: AsyncSession, group_id: str) -> None:
    """
    校验群成员结构完整性：成员必须为 agent 会话、拥有别名、绑定可用 Agent。
    存量异常引用在执行前检测到时应暂停群组，而非降级为普通会话。
    """
    members = await group_chat_crud.list_member_chats(db, group_id)
    # 保留成员 Master（用户本人）不计入最少成员数，也不要求绑定 Agent
    agent_members = [m for m in members if m.memberAlias != MASTER_ALIAS]
    if len(agent_members) < MIN_GROUP_MEMBERS:
        raise _bad(GroupErrorCode.STRUCTURE_INVALID, "member_count_below_minimum")
    aliases = set()
    for m in members:
        if not m.memberAlias:
            raise _bad(GroupErrorCode.STRUCTURE_INVALID, f"member_missing_alias:{m.id}")
        if len(m.memberAlias) > MEMBER_ALIAS_MAX_LEN:
            raise _bad(GroupErrorCode.STRUCTURE_INVALID, f"member_alias_too_long:{m.id}")
        if m.memberAlias in aliases:
            raise _bad(GroupErrorCode.STRUCTURE_INVALID, f"member_alias_dup:{m.memberAlias}")
        aliases.add(m.memberAlias)
        if m.memberAlias == MASTER_ALIAS:
            continue
        if not m.agentId:
            raise _bad(GroupErrorCode.STRUCTURE_INVALID, f"member_missing_agent:{m.id}")
        agent = await db.get(agent_model.Agent, m.agentId)
        if not agent or agent.itemType != AgentItemType.AGENT.value:
            raise _bad(GroupErrorCode.STRUCTURE_INVALID, f"member_agent_unavailable:{m.id}")


async def delete_group(db: AsyncSession, group_id: str) -> None:
    """
    生命周期感知的整组删除：删除 receipts、mails、tasks、state，再删除群及成员 Chat。
    调用方须确保群调度已停止（scheduler 层负责），此处只做数据清除。
    """
    group_node = await group_chat_crud.get_group_chat(db, group_id)
    if not group_node:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)

    from sqlalchemy import or_
    # 删除收件记录
    mail_ids_subq = select(group_chat_model.GroupMail.id).where(
        group_chat_model.GroupMail.groupId == group_id
    )
    await db.execute(
        delete(group_chat_model.GroupMailReceipt).where(
            or_(
                group_chat_model.GroupMailReceipt.mailId.in_(mail_ids_subq),
                group_chat_model.GroupMailReceipt.recipientChatId.in_(
                    select(chat_model.Chat.id).where(chat_model.Chat.parentId == group_id)
                ),
            )
        )
    )
    await db.execute(
        delete(group_chat_model.GroupMail).where(group_chat_model.GroupMail.groupId == group_id)
    )
    await db.execute(
        delete(group_chat_model.GroupTask).where(group_chat_model.GroupTask.groupId == group_id)
    )
    await db.execute(
        delete(group_chat_model.GroupState).where(group_chat_model.GroupState.groupId == group_id)
    )
    # 删除成员子会话
    await db.execute(
        delete(chat_model.Chat).where(chat_model.Chat.parentId == group_id)
    )
    # 删除群父节点
    await db.execute(
        delete(chat_model.Chat).where(chat_model.Chat.id == group_id)
    )
    await db.commit()


# ──────────────────────────────────────────────
# 审核模式：邮件审批
# ──────────────────────────────────────────────

async def mail_to_response(
    db: AsyncSession, mail: group_chat_model.GroupMail
) -> schemas.GroupMailResponse:
    return schemas.GroupMailResponse(
        id=mail.id,
        groupId=mail.groupId,
        sourceTaskId=mail.sourceTaskId,
        senderChatId=mail.senderChatId,
        senderAliasSnapshot=mail.senderAliasSnapshot,
        recipientSnapshot=mail.recipientSnapshot or [],
        title=mail.title,
        content=mail.content,
        attachments=await mail_service.mail_attachments_response(db, mail),
        state=mail.state,
        sequence=mail.sequence,
        createdAt=mail.createdAt,
        sentAt=mail.sentAt,
        reviewedAt=mail.reviewedAt,
        rejectReason=mail.rejectReason,
    )


async def get_group_mail_reviews(
    db: AsyncSession, group_id: str
) -> schemas.GroupMailReviewResponse:
    """审核视图：待审核邮件 + 已决策邮件（被拒 / 已同意待投递）。"""
    node = await group_chat_crud.get_group_chat(db, group_id)
    if not node:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)
    pending, decided = await mail_service.list_review_queue(db, group_id)
    return schemas.GroupMailReviewResponse(
        pending=[await mail_to_response(db, m) for m in pending],
        decided=[await mail_to_response(db, m) for m in decided],
    )


async def decide_group_mail(
    db: AsyncSession,
    group_id: str,
    mail_id: str,
    approve: bool,
    reason: Optional[str] = None,
) -> schemas.GroupMailDecisionResponse:
    """
    用户审核一封待投递邮件（同意 / 拒绝，拒绝原因必填）。
    同批（同一次轮次）最后一封处理完时定稿：
    - 无拒绝：立即正常投递（同自动模式），并顺带投递该发件人此前 deferred 的邮件；
    - 存在拒绝：同意的邮件转 deferred（本轮不投递、不触发收件人），并向发信人注入结果消息、触发其再生成一次。
    """
    if approve:
        outcome = await mail_service.approve_mail(db, group_id, mail_id)
        decided_state = GroupMailState.STAGED.value
    else:
        outcome = await mail_service.reject_mail(db, group_id, mail_id, reason or "")
        decided_state = GroupMailState.REJECTED.value

    if outcome.finalized:
        if outcome.decision_text and outcome.sender_chat_id:
            # 结果消息作为 user message 注入发信人子会话，并驱动其下一轮
            await generation_bridge.enqueue_member_turn(
                db,
                group_id=group_id,
                member_chat_id=outcome.sender_chat_id,
                kind=GroupTaskKind.USER_MESSAGE.value,
                payload={"content": outcome.decision_text},
            )

    state = await group_chat_crud.get_group_state(db, group_id)
    version = state.version if state else 0
    if outcome.finalized and state is not None:
        await events.publish_group_state_changed(
            group_id, state.version, state.status, state.pauseReason
        )
        for sent_mail_id, sequence in outcome.delivered:
            await events.publish_group_mail_sent(
                group_id, sent_mail_id, sequence, version=state.version
            )

    return schemas.GroupMailDecisionResponse(
        groupId=group_id,
        mailId=mail_id,
        state=GroupMailState(decided_state),
        pendingCount=outcome.pending,
        finalized=outcome.finalized,
        version=version,
    )
