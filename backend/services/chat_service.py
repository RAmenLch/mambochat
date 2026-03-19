# backend/services/chat_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional, List, Dict
import json
import re

from backend.crud import chat_crud
from backend import schemas
from backend.models import chat_model

async def duplicate_chat_with_messages(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """
    复制一个现有会话及其所有消息和子消息来创建一个新会话。
    这是一个包含业务逻辑的服务层函数。
    """
    original_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not original_chat or original_chat.itemType != 'chat':
        return None

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
        for msg in original_chat.messages:
            new_msg = chat_model.Message(
                role=msg.role,
                sortOrder=msg.sortOrder,
                chatId=new_chat.id
            )
            db.add(new_msg)
            await db.flush()

            new_sub_messages = [
                chat_model.SubMessage(
                    content=sub.content,
                    sortOrder=sub.sortOrder,
                    type=sub.type,
                    config=sub.config,
                    status=sub.status,
                    messageId=new_msg.id
                )
                for sub in msg.sub_messages
            ]
            db.add_all(new_sub_messages)

        await db.commit()
        await db.refresh(new_chat, ['messages'])

    return new_chat


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
