# backend/services/chat_status_service.py

"""
会话列表实时状态（生成中 / 未读 / 中断待审核）的聚合与广播。

设计要点（零 schema 变更）：
- generating：以 stream_manager 的进程内存态为权威（单进程部署）；
- pendingReview：活跃路径上 ReviewTool / AskUser 子消息仍未决（decision / answers 为空）；
- unread：活跃路径最后内容时间戳晚于 Chat.lastOpenedAt（既有字段即"已读水位"）。

所有内容判定都限定在"活跃路径"内，与前端 `_calculate_message_status` 口径一致，
避免被已放弃分支上的历史子消息误触发。群组父节点与群成员子会话不参与展示。
"""

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import message_crud
from backend.models import chat_model
from backend.schemas.enums import MessageStatus, SubMessageType
from backend.services.stream_manager_service import stream_manager

CHAT_STATUS_GENERATING = "generating"
CHAT_STATUS_REVIEW = "review"
CHAT_STATUS_UNREAD = "unread"
CHAT_STATUS_IDLE = "idle"

_BATCH_SIZE = 200


def _normalize(dt: Optional[datetime]) -> Optional[datetime]:
    """统一剥离时区，保证与 SQLite 读出的值可直接比较。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _idle_flags() -> Dict[str, bool]:
    return {"generating": False, "pendingReview": False, "unread": False}


def _derive_status(flags: Dict[str, bool]) -> str:
    if flags.get("pendingReview"):
        return CHAT_STATUS_REVIEW
    if flags.get("generating"):
        return CHAT_STATUS_GENERATING
    if flags.get("unread"):
        return CHAT_STATUS_UNREAD
    return CHAT_STATUS_IDLE


async def publish_chat_status(chat_id: str, flags: Dict[str, Any]) -> None:
    """向全局通知通道推送单个会话的状态（增量，供前端合并）。"""
    from backend.routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID

    payload = {
        "type": "chat_status",
        "payload": {
            "chat_id": chat_id,
            "status": _derive_status(flags),
            **{k: bool(v) for k, v in flags.items()},
        },
    }
    await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, payload)


async def compute_chat_statuses(
    db: AsyncSession, chat_ids: Iterable[str]
) -> Dict[str, Dict[str, bool]]:
    """
    批量计算会话状态，返回 {chat_id: {"generating", "pendingReview", "unread"}}。

    群父节点与群成员会话不会出现在结果中（不展示徽标）。
    """
    ids = [cid for cid in dict.fromkeys(chat_ids) if cid]
    if not ids:
        return {}

    generating_ids = await stream_manager.get_generating_chat_ids()
    result: Dict[str, Dict[str, bool]] = {}

    for start in range(0, len(ids), _BATCH_SIZE):
        batch = ids[start:start + _BATCH_SIZE]
        batch_result = await _compute_batch(db, batch, generating_ids)
        result.update(batch_result)

    return result


async def _compute_batch(
    db: AsyncSession, batch: List[str], generating_ids: set[str]
) -> Dict[str, Dict[str, bool]]:
    meta_rows = (
        await db.execute(
            select(
                chat_model.Chat.id,
                chat_model.Chat.itemType,
                chat_model.Chat.folderType,
                chat_model.Chat.memberAlias,
                chat_model.Chat.lastOpenedAt,
            ).where(chat_model.Chat.id.in_(batch))
        )
    ).all()

    displayable: Dict[str, Optional[datetime]] = {}
    for row in meta_rows:
        if row.itemType == "folder" or row.folderType == "group" or row.memberAlias:
            continue
        displayable[row.id] = _normalize(row.lastOpenedAt)

    if not displayable:
        return {}

    display_ids = list(displayable.keys())

    # 活跃路径：只有活跃路径上的消息才计入徽标判定（放弃分支上的历史子消息不参与）
    active_paths = await message_crud.get_active_path_message_ids(db, display_ids)
    msg_to_chat: Dict[str, str] = {}
    for chat_id, msg_ids in active_paths.items():
        for msg_id in msg_ids:
            msg_to_chat[msg_id] = chat_id

    review_map: Dict[str, bool] = {}
    content_map: Dict[str, Optional[datetime]] = {}

    active_msg_ids = list(msg_to_chat.keys())
    if active_msg_ids:
        review_rows = (
            await db.execute(
                select(
                    chat_model.SubMessage.messageId,
                    chat_model.SubMessage.type,
                    chat_model.SubMessage.content,
                )
                .where(
                    chat_model.SubMessage.messageId.in_(active_msg_ids),
                    chat_model.SubMessage.type.in_(
                        [SubMessageType.REVIEW_TOOL.value, SubMessageType.ASK_USER.value]
                    ),
                    chat_model.SubMessage.status == MessageStatus.PENDING_REVIEW.value,
                )
            )
        ).all()

        for row in review_rows:
            chat_id = msg_to_chat.get(row.messageId)
            if not chat_id or review_map.get(chat_id):
                continue
            if _is_undecided(row.type, row.content):
                review_map[chat_id] = True

        content_rows = (
            await db.execute(
                select(chat_model.Message.chatId, func.max(chat_model.SubMessage.createdAt))
                .join(chat_model.SubMessage, chat_model.SubMessage.messageId == chat_model.Message.id)
                .where(chat_model.Message.id.in_(active_msg_ids))
                .group_by(chat_model.Message.chatId)
            )
        ).all()
        content_map = {row[0]: _normalize(row[1]) for row in content_rows}

    result: Dict[str, Dict[str, bool]] = {}
    for chat_id in display_ids:
        last_opened = displayable[chat_id]
        last_content = content_map.get(chat_id)
        unread = last_content is not None and (
            last_opened is None or last_content > last_opened
        )
        result[chat_id] = {
            "generating": chat_id in generating_ids,
            "pendingReview": bool(review_map.get(chat_id)),
            "unread": bool(unread),
        }

    return result


def _is_undecided(sub_type: str, content: Optional[str]) -> bool:
    """复刻 `_calculate_message_status` 的未决判定：审核无 decision / 追问无 answers。"""
    if not content:
        return True
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return True
    if not isinstance(parsed, dict):
        return True
    if sub_type == SubMessageType.REVIEW_TOOL.value:
        return parsed.get("decision") is None
    return parsed.get("answers") is None


async def compute_chat_status(
    db: AsyncSession, chat_id: str
) -> Optional[Dict[str, bool]]:
    statuses = await compute_chat_statuses(db, [chat_id])
    return statuses.get(chat_id)


async def publish_current_status(chat_id: str) -> None:
    """用独立会话重算单个会话的完整状态并广播（生成结束 / 审核提交后调用）。"""
    from backend.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            flags = await compute_chat_status(db, chat_id)
    except Exception as e:
        print(f"[ChatStatus] Failed to compute status for chat '{chat_id}': {e}")
        return

    if flags is None:
        return
    await publish_chat_status(chat_id, flags)
