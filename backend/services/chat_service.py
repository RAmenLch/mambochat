# backend/services/chat_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional, List, Dict
import json
import re

from backend.crud import chat_crud
from backend import schemas
from backend.models import chat_model
from schemas import MessageStatus, MoveAction


async def duplicate_chat_with_messages(
    db: AsyncSession,
    chat_id: str,
    up_to_message_id: Optional[str] = None
) -> Optional[chat_model.Chat]:
    """
    复制一个现有会话及其消息。
    - 支持截断：如果提供 up_to_message_id，则仅复制排序位置小于等于该消息的数据。
    - 状态清洗：将 GENERATING 和 PENDING_REVIEW 等中间态统一置为 FAILED。
    """
    original_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not original_chat or original_chat.itemType != 'chat':
        return None

    # 获取当前父节点下的最大 sortOrder 用于新会话的排版
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

    # 1. 创建新会话主表信息
    new_chat_data = schemas.ChatCreate(
        name=f"{original_chat.name} (副本)",
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

    if original_chat.messages:
        # 2. 寻找截断参照的 sortOrder 值（防遍历顺序乱序隐患）
        cutoff_sort_order = float('inf')
        if up_to_message_id:
            for m in original_chat.messages:
                if m.id == up_to_message_id:
                    cutoff_sort_order = m.sortOrder
                    break

        # 3. 遍历复制消息主表和子表
        for msg in original_chat.messages:
            # 超过截断线的数据，直接忽略
            if msg.sortOrder > cutoff_sort_order:
                continue

            new_msg = chat_model.Message(
                role=msg.role,
                sortOrder=msg.sortOrder,
                chatId=new_chat.id
            )
            db.add(new_msg)
            await db.flush()

            new_sub_messages = []
            for sub in msg.sub_messages:
                # 状态防卡死清洗
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

    # 1. 自动创建一个用来归档的新文件夹
    # 默认让其排在目标层级的最后
    new_folder_data = schemas.ChatCreate(
        name=request.new_folder_name,
        itemType='folder',
        parentId=None if request.parent_id == 'root' else request.parent_id
    )
    new_folder = await chat_crud.create_chat(db, chat=new_folder_data)

    # 2. 复用底层 move_chats 能力，将传入的 item_ids 批量移入新文件夹内部
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
        # 如果正则无效，返回开头部分
        return content[:window_size * 2]

    if not match:
        return content[:window_size * 2]

    start, end = match.span()
    total_len = len(content)

    # 计算截取范围
    snippet_start = max(0, start - window_size)
    snippet_end = min(total_len, end + window_size)

    snippet = content[snippet_start:snippet_end]

    # 添加省略号
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

    # 获取所有相关的祖先节点
    rows = await chat_crud.get_batch_chat_ancestors(db, chat_ids)

    # 构建节点查找表: id -> {name, parentId}
    node_map = {row.id: {"name": row.name, "parentId": row.parentId} for row in rows}

    paths = {}
    for start_id in chat_ids:
        if start_id not in node_map:
            continue

        current_id = start_id
        path_segments = []

        # 向上遍历直到根节点
        while current_id:
            node = node_map.get(current_id)
            if not node:
                break
            path_segments.append(node["name"])
            current_id = node["parentId"]

        # 移除自身节点（路径通常指父级目录结构）
        if path_segments:
            path_segments.pop(0)

        # 反转列表并拼接，形成 Root / Folder / ...
        paths[start_id] = " / ".join(reversed(path_segments))

    return paths
