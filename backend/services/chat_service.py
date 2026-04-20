# backend/services/chat_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional, List, Dict
import json
import re

from backend.crud import chat_crud, message_crud, setting_crud
from backend import schemas
from backend.models import chat_model
from backend.schemas.enums import MessageStatus, MoveAction


async def duplicate_chat_with_messages(
    db: AsyncSession,
    chat_id: str,
    up_to_message_id: Optional[str] = None
) -> Optional[chat_model.Chat]:
    """
    复制一个现有会话及其活跃路径上的消息。
    - 支持截断：如果提供 up_to_message_id，则仅复制该消息及之前的活跃路径数据。
    - 状态清洗：将 GENERATING 和 PENDING_REVIEW 等中间态统一置为 FAILED。
    """
    original_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not original_chat or original_chat.itemType != 'chat':
        return None

    lang_setting = await setting_crud.get_setting(db, "language")
    language = lang_setting.value if lang_setting else "zh-CN"
    copy_suffix = "副本" if language == "zh-CN" else "Copy"

    max_sort_order_result = await db.execute(
        select(func.max(chat_model.Chat.sortOrder))
        .filter(chat_model.Chat.parentId == original_chat.parentId)
    )
    max_sort_order = max_sort_order_result.scalar_one_or_none()
    new_sort_order = (max_sort_order or 0) + 1

    try:
        params = json.loads(original_chat.modelParameters) if original_chat.modelParameters else None
    except json.JSONDecodeError:
        params = None

    new_chat_data = schemas.ChatCreate(
        name=f"{original_chat.name} ({copy_suffix})",
        systemPrompt=original_chat.systemPrompt,
        modelParameters=params,
        aiModelId=original_chat.aiModelId,
        itemType='chat',
        parentId=original_chat.parentId,
        sortOrder=new_sort_order,
        resource_prompt_list=original_chat.resource_prompt_list,
        enabled_mcp_ids=original_chat.enabled_mcp_ids,
        chatMode=original_chat.chatMode,
        agentId=original_chat.agentId
    )
    new_chat = await chat_crud.create_chat(db, chat=new_chat_data)

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)

    if active_messages:
        if up_to_message_id:
            cutoff_index = -1
            for i, m in enumerate(active_messages):
                if m.id == up_to_message_id:
                    cutoff_index = i
                    break
            if cutoff_index != -1:
                active_messages = active_messages[:cutoff_index + 1]

        last_new_msg_id = None
        for msg in active_messages:
            new_msg = chat_model.Message(
                role=msg.role,
                sortOrder=msg.sortOrder,
                chatId=new_chat.id,
                parentId=last_new_msg_id,
                lastActiveAt=msg.lastActiveAt
            )
            db.add(new_msg)
            await db.flush()
            last_new_msg_id = new_msg.id

            new_sub_messages = []
            for sub in msg.sub_messages:
                safe_status = sub.status
                if safe_status in [MessageStatus.GENERATING.value, MessageStatus.PENDING_REVIEW.value]:
                    safe_status = MessageStatus.FAILED.value

                new_sub_messages.append(
                    chat_model.SubMessage(
                        content=sub.content,
                        sortOrder=sub.sortOrder,
                        type=sub.type,
                        config=sub.config,
                        status=safe_status,
                        messageId=new_msg.id
                    )
                )
            db.add_all(new_sub_messages)

        await db.commit()
        await db.refresh(new_chat, ['messages'])

    return new_chat


async def archive_chats_to_new_folder(db: AsyncSession, request: schemas.ChatArchiveRequest) -> Optional[chat_model.Chat]:
    """
    新建一个文件夹，并将指定的会话批量归档/移动到该文件夹中
    """
    if not request.item_ids:
        return None

    new_folder_data = schemas.ChatCreate(
        name=request.new_folder_name,
        itemType='folder',
        parentId=None if request.parent_id == 'root' else request.parent_id
    )
    new_folder = await chat_crud.create_chat(db, chat=new_folder_data)

    move_request = schemas.ChatMoveRequest(
        item_ids=request.item_ids,
        reference_id=new_folder.id,
        action=MoveAction.INSIDE
    )
    success = await chat_crud.move_chats(db, move_request=move_request)
    if not success:
        return None

    await db.refresh(new_folder)
    return new_folder


def extract_context_snippet(content: str, keyword: str, enable_regex: bool, window_size: int = 50) -> str:
    """
    从文本中截取包含关键词的上下文片段。
    """
    if not content:
        return ""

    flags = re.IGNORECASE
    if enable_regex:
        pattern = keyword
    else:
        pattern = re.escape(keyword)

    try:
        match = re.search(pattern, content, flags)
    except re.error:
        return content[:window_size * 2]

    if not match:
        return content[:window_size * 2]

    start, end = match.span()
    total_len = len(content)

    snippet_start = max(0, start - window_size)
    snippet_end = min(total_len, end + window_size)

    snippet = content[snippet_start:snippet_end]

    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < total_len:
        snippet = snippet + "..."

    return snippet


async def build_chat_paths(db: AsyncSession, chat_ids: List[str]) -> Dict[str, str]:
    """
    批量构建会话的路径字符串（例如：Folder A / Folder B）。
    返回字典: {chat_id: path_string}
    """
    if not chat_ids:
        return {}

    rows = await chat_crud.get_batch_chat_ancestors(db, chat_ids)

    node_map = {row.id: {"name": row.name, "parentId": row.parentId} for row in rows}

    paths = {}
    for start_id in chat_ids:
        if start_id not in node_map:
            continue

        current_id = start_id
        path_segments = []

        while current_id:
            node = node_map.get(current_id)
            if not node:
                break
            path_segments.append(node["name"])
            current_id = node["parentId"]

        if path_segments:
            path_segments.pop(0)

        paths[start_id] = " / ".join(reversed(path_segments))

    return paths
