# backend/services/group_chat/service.py

"""
群组会话服务：原子建群、群详情、生命周期删除、成员与结构校验。

本模块只负责群组这一业务实体的结构完整性，不承担邮件调度与生成桥接
（见 mail_service / scheduler / generation_bridge）。
"""

import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.models import chat_model, agent_model, group_chat_model
from backend.crud import group_chat_crud
from backend.schemas.enums import (
    FolderType, GroupStatus, GroupPauseReason, GroupMailState, GroupTaskState, AgentItemType,
)
from backend.schemas.group_chat import (
    GroupChatCreate, GroupSettingsUpdate, normalize_member_alias,
    MEMBER_ALIAS_MAX_LEN,
)
from backend.exceptions import AppHTTPException
from backend.config.timezone_config import get_configured_now

logger = logging.getLogger(__name__)

MIN_GROUP_MEMBERS = 3


class GroupErrorCode:
    NOT_FOUND = "GROUP_NOT_FOUND"
    MEMBER_COUNT_INVALID = "GROUP_MEMBER_COUNT_INVALID"
    ALIAS_DUPLICATE = "GROUP_ALIAS_DUPLICATE"
    ALIAS_INVALID = "GROUP_ALIAS_INVALID"
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
        seen.add(alias)
        normalized_aliases.append(alias)

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
            nextTaskSeq=0,
            nextMailSeq=0,
            version=0,
        )
        db.add(state)

        member_nodes: List[chat_model.Chat] = []
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


def _build_detail(
    group_node: chat_model.Chat,
    state: group_chat_model.GroupState,
    member_nodes: List[chat_model.Chat],
    agent_names: Dict[str, str],
    unread_map: Dict[str, int],
    queued_map: Dict[str, int],
) -> schemas.GroupCreatedResponse:
    members = [
        schemas.GroupMemberResponse(
            chatId=m.id,
            memberAlias=m.memberAlias,
            agentId=m.agentId,
            agentName=agent_names.get(m.agentId) if m.agentId else None,
            name=m.name,
            sortOrder=m.sortOrder,
            unreadCount=unread_map.get(m.id, 0),
            pendingCount=queued_map.get(m.id, 0),
        )
        for m in member_nodes
    ]
    total_unread = sum(unread_map.values())
    total_queued = sum(queued_map.values())
    return schemas.GroupCreatedResponse(
        groupId=group_node.id,
        name=group_node.name,
        parentId=group_node.parentId,
        status=GroupStatus(state.status),
        pauseReason=state.pauseReason,
        autoRoundLimit=state.autoRoundLimit,
        autoRoundCount=state.autoRoundCount,
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
    return _build_detail(
        group_node, state, member_nodes, agent_names, unread_map, queued_map
    )


async def update_group_settings(
    db: AsyncSession, group_id: str, payload: GroupSettingsUpdate
) -> schemas.GroupControlResponse:
    state = await group_chat_crud.get_group_state(db, group_id)
    if not state:
        raise _bad(GroupErrorCode.NOT_FOUND, "group_not_found", 404)

    if payload.autoRoundLimit is not None:
        state.autoRoundLimit = payload.autoRoundLimit
    if payload.resetAutoRoundCount:
        state.autoRoundCount = 0
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
    if len(members) < MIN_GROUP_MEMBERS:
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
