# backend/services/group_chat/guards.py

"""
群组结构保护：阻止普通创建/移动/reorder/更新/删除/复制/归档等操作绕过固定成员限制。

这些校验在路由层调用，保持既有 CRUD 事务语义不变。
"""

from typing import List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import chat_model, group_chat_model, agent_model
from backend.schemas.enums import FolderType, MoveAction
from backend.exceptions import AppHTTPException


def _forbidden(detail: str) -> AppHTTPException:
    return AppHTTPException(
        status_code=400, error_code="GROUP_FORBIDDEN_OPERATION", detail=detail
    )


async def is_group(db: AsyncSession, chat_id: Optional[str]) -> bool:
    if not chat_id or chat_id == "root":
        return False
    result = await db.execute(
        select(chat_model.Chat.id).filter(
            chat_model.Chat.id == chat_id,
            chat_model.Chat.itemType == "folder",
            chat_model.Chat.folderType == FolderType.GROUP.value,
        )
    )
    return result.scalar() is not None


async def _is_member(db: AsyncSession, chat_id: str) -> bool:
    result = await db.execute(
        select(chat_model.Chat.memberAlias).filter(chat_model.Chat.id == chat_id)
    )
    return result.scalar() is not None


async def assert_parent_allows_creation(db: AsyncSession, parent_id: Optional[str]) -> None:
    """禁止在群组父节点内部创建普通节点。"""
    if parent_id in (None, "", "root"):
        return
    if await is_group(db, parent_id):
        raise _forbidden("cannot_create_inside_group")


async def _resolve_target_parent(
    db: AsyncSession, item_id: str, reference_id: str, action: MoveAction
) -> Optional[str]:
    if action == MoveAction.INSIDE:
        return None if reference_id == "root" else reference_id
    ref_chat = await db.get(chat_model.Chat, reference_id)
    return ref_chat.parentId if ref_chat else None


async def assert_move_allowed(db, move_request) -> None:
    """
    移动规则：
    - 群成员不可被移出；
    - 群组整体可移动到普通文件夹，但禁止嵌套群组；
    - 禁止把任意节点移动到群组父节点内部。
    """
    target_parent = await _resolve_target_parent(
        db, "", move_request.reference_id, move_request.action
    )
    if target_parent and await is_group(db, target_parent):
        raise _forbidden("cannot_move_inside_group")

    for item_id in move_request.item_ids:
        if await _is_member(db, item_id):
            raise _forbidden("cannot_move_group_member")
        if await is_group(db, item_id):
            # 群整体移动：目标父节点不得是群（已在上面拦截）
            if target_parent and await is_group(db, target_parent):
                raise _forbidden("nested_group_forbidden")


async def assert_reorder_allowed(db: AsyncSession, updates) -> None:
    for update_item in updates:
        if await _is_member(db, update_item.id):
            chat = await db.get(chat_model.Chat, update_item.id)
            if chat and chat.parentId != update_item.parentId:
                raise _forbidden("cannot_move_group_member")
        if update_item.parentId and await is_group(db, update_item.parentId):
            raise _forbidden("cannot_move_inside_group")


async def assert_update_allowed(db, chat_id: str, chat_update) -> None:
    """
    更新规则：
    - 群成员不可换绑 Agent、不可改变 chatMode、不可移出群；
    - 群父节点不可改 chatMode/agentId（保持 folder 语义）。
    名称（标题）修改允许，不影响邮箱别名。
    """
    fields: Set[str] = set(chat_update.model_dump(exclude_unset=True).keys())
    chat = await db.get(chat_model.Chat, chat_id)
    if chat is None:
        return

    if chat.memberAlias:
        if "parentId" in fields:
            raise _forbidden("cannot_move_group_member")
        if "agentId" in fields:
            raise _forbidden("cannot_rebind_group_member_agent")
        if "chatMode" in fields:
            raise _forbidden("cannot_change_group_member_mode")

    if chat.folderType == FolderType.GROUP.value:
        if "agentId" in fields or "chatMode" in fields:
            raise _forbidden("cannot_modify_group_parent_mode")
        if "parentId" in fields:
            new_parent = chat_update.parentId
            if new_parent and await is_group(db, new_parent):
                raise _forbidden("nested_group_forbidden")


async def assert_duplicate_allowed(db, chat_id: str) -> None:
    """禁止复制群成员（会破坏别名唯一与成员绑定）；群父节点本就不支持复制。"""
    if await _is_member(db, chat_id):
        raise _forbidden("cannot_duplicate_group_member")
    if await is_group(db, chat_id):
        raise _forbidden("cannot_duplicate_group")


async def collect_descendant_group_ids(db, chat_id: str) -> List[str]:
    """返回子树中（含自身）所有群父节点的 ID。"""
    from backend.crud.chat_crud import get_descendant_chat_ids
    descendants = await get_descendant_chat_ids(db, chat_id)
    if not descendants:
        return []
    result = await db.execute(
        select(chat_model.Chat.id).filter(
            chat_model.Chat.id.in_(descendants),
            chat_model.Chat.folderType == FolderType.GROUP.value,
        )
    )
    return list(result.scalars().all())


async def purge_group_business_data(db: AsyncSession, group_id: str) -> None:
    """
    仅删除群组业务数据（receipts / mails / tasks / state），不删除 Chat 节点。
    用于删除普通父文件夹时清理其后代群组。调用方负责 commit。
    """
    from sqlalchemy import delete, or_
    member_ids = select(chat_model.Chat.id).where(chat_model.Chat.parentId == group_id)
    mail_ids = select(group_chat_model.GroupMail.id).where(
        group_chat_model.GroupMail.groupId == group_id
    )
    await db.execute(
        delete(group_chat_model.GroupMailReceipt).where(
            or_(
                group_chat_model.GroupMailReceipt.mailId.in_(mail_ids),
                group_chat_model.GroupMailReceipt.recipientChatId.in_(member_ids),
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


async def assert_archive_allowed(db, item_ids, parent_id) -> None:
    """归档：禁止把群成员单独归档；新文件夹不得落在群内。"""
    if parent_id not in (None, "", "root") and await is_group(db, parent_id):
        raise _forbidden("cannot_archive_inside_group")
    for item_id in item_ids:
        if await _is_member(db, item_id):
            raise _forbidden("cannot_archive_group_member")


async def assert_export_allowed(db: AsyncSession, chat_id: str) -> None:
    """群组及群成员不支持按普通导出格式导出（会丢失成员关系与邮件）。"""
    if await _is_member(db, chat_id):
        raise _forbidden("cannot_export_group_member")
    if await is_group(db, chat_id):
        raise _forbidden("cannot_export_group")


async def assert_agent_deletable(db: AsyncSession, agent_id: str) -> None:
    """
    被群成员引用的 Agent 不可删除。
    调用方需对 Agent 文件夹的后代 Agent 逐一校验。
    """
    result = await db.execute(
        select(chat_model.Chat.id).filter(
            chat_model.Chat.agentId == agent_id,
            chat_model.Chat.memberAlias.isnot(None),
        ).limit(1)
    )
    if result.scalar() is not None:
        raise AppHTTPException(
            status_code=409,
            error_code="GROUP_AGENT_REFERENCED",
            detail="agent_referenced_by_group_member",
        )


async def _collect_descendant_agent_ids(db: AsyncSession, agent_id: str) -> List[str]:
    cte = select(agent_model.Agent.id).where(agent_model.Agent.id == agent_id).cte(
        name="agent_desc", recursive=True
    )
    cte = cte.union_all(
        select(agent_model.Agent.id).join(cte, agent_model.Agent.parentId == cte.c.id)
    )
    result = await db.execute(select(cte.c.id))
    return list(result.scalars().all())


async def assert_agents_deletable(db: AsyncSession, agent_id: str) -> None:
    """
    删除 Agent/Agent 文件夹前，检查其后代 Agent 是否被固定群成员引用。
    被引用时返回引用冲突，避免固定成员失效。
    """
    ids = await _collect_descendant_agent_ids(db, agent_id)
    if not ids:
        return
    result = await db.execute(
        select(chat_model.Chat.id).filter(
            chat_model.Chat.agentId.in_(ids),
            chat_model.Chat.memberAlias.isnot(None),
        ).limit(1)
    )
    if result.scalar() is not None:
        raise AppHTTPException(
            status_code=409,
            error_code="GROUP_AGENT_REFERENCED",
            detail="agent_referenced_by_group_member",
        )
