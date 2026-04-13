# backend/crud/chat_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func, literal, union_all, null, case, literal_column, or_, update
from typing import List, Optional, Tuple, Any
import json

from backend.models import chat_model, provider_model
from backend.schemas.enums import SubMessageType, MoveAction
from backend import schemas
from backend.config.timezone_config import get_configured_now


async def get_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """通过ID获取单个聊天会话（包含其所有消息、子消息、模型和提供商信息）"""
    result = await db.execute(
        select(chat_model.Chat)
        .options(
            selectinload(chat_model.Chat.messages).selectinload(chat_model.Message.sub_messages),
            joinedload(chat_model.Chat.ai_model).joinedload(provider_model.AIModel.provider)
        )
        .filter(chat_model.Chat.id == chat_id)
    )
    return result.scalars().first()


async def get_chats(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[chat_model.Chat]:
    """获取会话和文件夹列表（按排序权重升序）"""
    result = await db.execute(
        select(chat_model.Chat)
        .order_by(chat_model.Chat.sortOrder.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def get_chats_by_parent_ids(db: AsyncSession, parent_ids: List[str]) -> List[chat_model.Chat]:
    """
    根据父节点ID列表批量获取子会话和文件夹。
    如果列表中包含 "root"，则同时获取根目录下的项目。
    """
    if not parent_ids:
        return []

    conditions = []
    valid_uuids = [pid for pid in parent_ids if pid != "root"]

    if valid_uuids:
        conditions.append(chat_model.Chat.parentId.in_(valid_uuids))

    if "root" in parent_ids:
        conditions.append(chat_model.Chat.parentId.is_(None))

    if not conditions:
        return []

    result = await db.execute(
        select(chat_model.Chat)
        .filter(or_(*conditions))
        .order_by(chat_model.Chat.sortOrder.asc())
    )
    return result.scalars().all()


async def create_chat(db: AsyncSession, chat: schemas.ChatCreate) -> chat_model.Chat:
    """创建一个新的聊天会话或文件夹"""

    # 如果未传 sortOrder，则计算追加到末尾的顺序值
    if "sortOrder" not in chat.model_fields_set:
        stmt = select(func.max(chat_model.Chat.sortOrder)).filter(
            chat_model.Chat.parentId == chat.parentId
        )
        result = await db.execute(stmt)
        max_order = result.scalar()
        # 如果文件夹为空(None)，则从 0 开始；否则在最大值基础上 +1
        chat.sortOrder = (max_order if max_order is not None else -1) + 1

    chat_data = chat.model_dump()
    if chat_data.get("modelParameters") is not None:
        chat_data["modelParameters"] = json.dumps(chat_data["modelParameters"])

    db_chat = chat_model.Chat(**chat_data)
    db.add(db_chat)
    await db.commit()
    await db.refresh(db_chat)
    return db_chat


async def update_chat(db: AsyncSession, chat_id: str, chat_update: schemas.ChatUpdate) -> Optional[chat_model.Chat]:
    """更新会话或文件夹的配置信息"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if not db_chat:
        return None

    update_data = chat_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if key == "modelParameters" and value is not None:
            setattr(db_chat, key, json.dumps(value))
        else:
            setattr(db_chat, key, value)

    await db.commit()
    await db.refresh(db_chat)
    return db_chat


async def get_descendant_chat_ids(db: AsyncSession, chat_id: str) -> List[str]:
    """
    递归获取指定节点的所有后代 Chat ID（包括自身）。
    用于删除前清理 LangGraph checkpoint。
    """
    cte = select(chat_model.Chat.id).where(chat_model.Chat.id == chat_id).cte(name="descendants", recursive=True)
    cte = cte.union_all(
        select(chat_model.Chat.id).join(cte, chat_model.Chat.parentId == cte.c.id)
    )
    result = await db.execute(select(cte.c.id))
    return list(result.scalars().all())


async def delete_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """删除一个聊天会话或文件夹"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if db_chat:
        await db.delete(db_chat)
        await db.commit()
    return db_chat


async def touch_chat(db: AsyncSession, chat_id: str) -> Optional[chat_model.Chat]:
    """更新会话的 lastOpenedAt 时间戳"""
    db_chat = await get_chat(db, chat_id=chat_id)
    if db_chat:
        db_chat.lastOpenedAt = get_configured_now()
        await db.commit()
        await db.refresh(db_chat)
    return db_chat


async def batch_update_chats_order(db: AsyncSession, updates: List[schemas.ChatReorderItem]) -> bool:
    """批量更新会话和文件夹的顺序与层级"""
    if not updates:
        return True

    chat_ids = [item.id for item in updates]
    result = await db.execute(select(chat_model.Chat).filter(chat_model.Chat.id.in_(chat_ids)))
    chats_map = {chat.id: chat for chat in result.scalars().all()}

    for update_item in updates:
        chat_to_update = chats_map.get(update_item.id)
        if chat_to_update:
            chat_to_update.parentId = update_item.parentId
            chat_to_update.sortOrder = update_item.sortOrder

    await db.commit()
    return True


async def move_chats(db: AsyncSession, move_request: schemas.ChatMoveRequest) -> bool:
    """
    移动会话或文件夹到指定位置（Inside, Before, After）。
    处理目标位置的排序挤占逻辑。
    """
    if not move_request.item_ids:
        return True

    target_parent_id = None
    target_sort_order = 0

    # 1. 计算目标父节点和起始排序值
    if move_request.action == MoveAction.INSIDE:
        # 移入文件夹内部，作为最后一个子节点
        if move_request.reference_id != "root":
            target_parent_id = move_request.reference_id

        # 获取目标文件夹内当前最大的 sortOrder
        stmt = select(func.max(chat_model.Chat.sortOrder)).filter(chat_model.Chat.parentId == target_parent_id)
        result = await db.execute(stmt)
        max_order = result.scalar()
        target_sort_order = (max_order if max_order is not None else -1) + 1

    else:
        # Before 或 After，需要参考节点
        if move_request.reference_id == "root":
            # 根节点不能作为 Before/After 的参考对象，除非业务逻辑允许将项目放在“根”之前/之后（通常无意义）
            # 这里假设 reference_id 必须是具体的 item ID
            return False

        ref_chat = await db.get(chat_model.Chat, move_request.reference_id)
        if not ref_chat:
            return False

        target_parent_id = ref_chat.parentId
        base_order = ref_chat.sortOrder

        if move_request.action == MoveAction.BEFORE:
            target_sort_order = base_order
        else:  # AFTER
            target_sort_order = base_order + 1

        # 2. 挤占位移：将插入点之后的同级节点 sortOrder 向后推
        shift_stmt = (
            update(chat_model.Chat)
            .where(chat_model.Chat.parentId == target_parent_id)
            .where(chat_model.Chat.sortOrder >= target_sort_order)
            .values(sortOrder=chat_model.Chat.sortOrder + len(move_request.item_ids))
        )
        await db.execute(shift_stmt)

    # 3. 更新被移动的节点
    # 保持 item_ids 原有的相对顺序
    for index, item_id in enumerate(move_request.item_ids):
        stmt = (
            update(chat_model.Chat)
            .where(chat_model.Chat.id == item_id)
            .values(
                parentId=target_parent_id,
                sortOrder=target_sort_order + index
            )
        )
        await db.execute(stmt)

    await db.commit()
    return True


async def search_chats_and_messages(
    db: AsyncSession,
    keyword: str,
    root_id: Optional[str],
    enable_regex: bool,
    skip: int,
    limit: int
) -> Tuple[List[Any], int]:
    """
    全局搜索会话和消息内容。
    返回: (结果列表, 总数)
    结果列表中的每一项包含: chat_id, chat_name, sub_message_id, raw_content, match_type, created_at
    """

    # 1. 准备过滤条件
    if enable_regex:
        # 使用 SQLite 自定义函数 REGEXP
        def match_op(column):
            return column.op("REGEXP")(keyword)
    else:
        # 使用 LIKE 模糊匹配
        search_pattern = f"%{keyword}%"
        def match_op(column):
            return column.like(search_pattern)

    # 2. 如果指定了 root_id，构建递归 CTE 以获取所有子孙 Chat ID
    target_chat_ids_query = None
    if root_id:
        hierarchy_cte = select(chat_model.Chat.id).where(chat_model.Chat.id == root_id).cte(name="hierarchy", recursive=True)
        hierarchy_cte = hierarchy_cte.union_all(
            select(chat_model.Chat.id).join(hierarchy_cte, chat_model.Chat.parentId == hierarchy_cte.c.id)
        )
        target_chat_ids_query = select(hierarchy_cte.c.id)

    # 3. 构建 SubMessage 内容搜索查询
    # 筛选条件: SubMessage 类型为 Normal/Reasoning, Chat 类型为 chat, 且满足 keyword 和 root_id
    q_sub = select(
        chat_model.Chat.id.label("chat_id"),
        chat_model.Chat.name.label("chat_name"),
        chat_model.SubMessage.id.label("sub_message_id"),
        chat_model.SubMessage.content.label("raw_content"),
        literal("content").label("match_type"),
        chat_model.SubMessage.createdAt.label("created_at")
    ).join(
        chat_model.Message, chat_model.SubMessage.messageId == chat_model.Message.id
    ).join(
        chat_model.Chat, chat_model.Message.chatId == chat_model.Chat.id
    ).where(
        chat_model.SubMessage.type.in_([SubMessageType.NORMAL, SubMessageType.REASONING]),
        chat_model.Chat.itemType == 'chat',
        match_op(chat_model.SubMessage.content)
    )

    if target_chat_ids_query is not None:
        q_sub = q_sub.where(chat_model.Chat.id.in_(target_chat_ids_query))

    # 4. 构建 Chat 元数据 (Title, SystemPrompt) 搜索查询
    # 逻辑: 优先匹配 Title，如果 Title 不匹配则认为匹配的是 SystemPrompt
    name_match = match_op(chat_model.Chat.name)
    sys_prompt_match = match_op(chat_model.Chat.systemPrompt)

    q_chat = select(
        chat_model.Chat.id.label("chat_id"),
        chat_model.Chat.name.label("chat_name"),
        null().label("sub_message_id"), # Chat 匹配没有 sub_message_id
        case(
            (name_match, chat_model.Chat.name),
            else_=chat_model.Chat.systemPrompt
        ).label("raw_content"),
        case(
            (name_match, literal("title")),
            else_=literal("system_prompt")
        ).label("match_type"),
        chat_model.Chat.createdAt.label("created_at")
    ).where(
        chat_model.Chat.itemType == 'chat',
        (name_match | sys_prompt_match)
    )

    if target_chat_ids_query is not None:
        q_chat = q_chat.where(chat_model.Chat.id.in_(target_chat_ids_query))

    # 5. 合并查询 (Union All)
    union_query = union_all(q_sub, q_chat).subquery()

    # 6. 获取总数 (Count)
    count_stmt = select(func.count()).select_from(union_query)
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    if total_count == 0:
        return [], 0

    # 7. 获取分页结果
    stmt = select(union_query).order_by(union_query.c.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total_count


async def get_batch_chat_ancestors(db: AsyncSession, chat_ids: List[str]) -> List[chat_model.Chat]:
    """
    批量获取指定 Chat 列表的所有祖先节点（包括自身），用于构建路径。
    先通过 CTE 获取 ID 列表，再查询完整对象以满足 Schema 要求。
    """
    if not chat_ids:
        return []

    # 1. 递归 CTE: 只查询 ID 和 parentId 以建立层级关系
    # 初始集：目标节点
    cte = select(
        chat_model.Chat.id,
        chat_model.Chat.parentId
    ).where(chat_model.Chat.id.in_(chat_ids)).cte(name="ancestors", recursive=True)

    # 递归部分：查找父节点
    cte = cte.union_all(
        select(
            chat_model.Chat.id,
            chat_model.Chat.parentId
        ).join(cte, chat_model.Chat.id == cte.c.parentId)
    )

    # 2. 获取所有涉及的 ID
    stmt = select(cte.c.id)
    result = await db.execute(stmt)
    ancestor_ids = result.scalars().all()

    if not ancestor_ids:
        return []

    # 3. 查询完整的 ORM 对象
    # 这样可以确保返回包含 createdAt, sortOrder 等所有字段的完整对象
    chats_result = await db.execute(
        select(chat_model.Chat)
        .where(chat_model.Chat.id.in_(ancestor_ids))
    )

    return chats_result.scalars().all()
