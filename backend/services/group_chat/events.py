# backend/services/group_chat/events.py

"""
群组事件发布。复用现有全局通知通道，事件类型与架构规划 §7.2 对齐：
group_created / group_state_changed / group_task_changed / group_mail_sent / group_deleted。

事件只携带路由与对账所需的最小信息（groupId、version、taskId/mailId 等），
邮件正文通过分页接口获取，不在全局事件中重复广播。
"""

from typing import Any, Dict, Optional

from backend.services.stream_manager_service import stream_manager


async def _publish(category: str, context: Dict[str, Any], message: str = "") -> None:
    from backend.routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID

    await stream_manager.publish(
        GLOBAL_NOTIFICATIONS_STREAM_ID,
        {
            "type": "notification",
            "category": category,
            "context": context,
            "level": "info",
            "message": message,
        },
    )


async def publish_group_created(group_id: str, version: int = 0) -> None:
    await _publish("group_created", {"groupId": group_id, "version": version})


async def publish_group_deleted(group_id: str) -> None:
    await _publish("group_deleted", {"groupId": group_id})


async def publish_group_state_changed(
    group_id: str, version: int, status: Optional[str] = None, pause_reason: Optional[str] = None
) -> None:
    await _publish(
        "group_state_changed",
        {
            "groupId": group_id,
            "version": version,
            "status": status,
            "pauseReason": pause_reason,
        },
    )


async def publish_group_task_changed(
    group_id: str, task_id: str, member_chat_id: str, state: str, version: int = 0,
    assistant_message_id: Optional[str] = None,
) -> None:
    await _publish(
        "group_task_changed",
        {
            "groupId": group_id,
            "version": version,
            "taskId": task_id,
            "memberChatId": member_chat_id,
            "state": state,
            "assistantMessageId": assistant_message_id,
        },
    )


async def publish_group_mail_sent(group_id: str, mail_id: str, sequence: Optional[int], version: int = 0) -> None:
    await _publish(
        "group_mail_sent",
        {
            "groupId": group_id,
            "version": version,
            "mailId": mail_id,
            "sequence": sequence,
        },
    )
