# backend/crud/agent_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update, or_
from typing import List, Optional

from backend.models import agent_model
from backend import schemas
from backend.schemas.enums import MoveAction, AgentTypeEnum

# Agent ORM 表的所有列名集合（用于 update_agent 显式过滤，替代 hasattr 鸭子判断）
_AGENT_COLUMNS: frozenset[str] = frozenset(agent_model.Agent.__table__.columns.keys())


async def check_subagent_cycle(db: AsyncSession, target_agent_id: str, new_subagents: List[str]) -> bool:
    """检查更新 subAgents 是否会引起循环依赖"""
    if not new_subagents:
        return False

    queue = list(new_subagents)
    visited = set()

    while queue:
        current_id = queue.pop(0)

        if current_id == target_agent_id:
            return True

        if current_id in visited:
            continue

        visited.add(current_id)

        stmt = select(agent_model.Agent.subAgents).where(agent_model.Agent.id == current_id)
        result = await db.execute(stmt)
        current_subagents = result.scalar()

        if current_subagents and isinstance(current_subagents, list):
            queue.extend(current_subagents)

    return False


async def get_agent(db: AsyncSession, agent_id: str) -> Optional[agent_model.Agent]:
    """通过ID获取单个 Agent（或文件夹）"""
    result = await db.execute(
        select(agent_model.Agent).filter(agent_model.Agent.id == agent_id)
    )
    return result.scalars().first()


async def get_agents(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[agent_model.Agent]:
    """获取 Agent 和文件夹列表（按排序权重升序）"""
    result = await db.execute(
        select(agent_model.Agent)
        .order_by(agent_model.Agent.sortOrder.asc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_agents_by_parent_ids(db: AsyncSession, parent_ids: List[str]) -> List[agent_model.Agent]:
    """
    根据父节点ID列表批量获取子节点。
    如果列表中包含 "root"，则同时获取根目录下的项目。
    """
    if not parent_ids:
        return []

    conditions = []
    valid_uuids = [pid for pid in parent_ids if pid != "root"]

    if valid_uuids:
        conditions.append(agent_model.Agent.parentId.in_(valid_uuids))

    if "root" in parent_ids:
        conditions.append(agent_model.Agent.parentId.is_(None))

    if not conditions:
        return []

    result = await db.execute(
        select(agent_model.Agent)
        .filter(or_(*conditions))
        .order_by(agent_model.Agent.sortOrder.asc())
    )
    return list(result.scalars().all())


async def create_agent(db: AsyncSession, agent: schemas.AgentCreate) -> agent_model.Agent:
    """创建一个新的 Agent 或文件夹"""

    # 同父目录下名称唯一（folder/agent 共享同名池子，保证路径寻址无歧义）
    existing = await _find_sibling_by_name(db, agent.parentId, agent.name)
    if existing:
        raise ValueError(
            f"同目录下已存在同名节点: '{agent.name}'（{existing.id[:8]}）。"
            "同一文件夹下名称必须唯一。"
        )

    # 如果未传 sortOrder，则计算追加到末尾的顺序值
    if "sortOrder" not in agent.model_fields_set:
        stmt = select(func.max(agent_model.Agent.sortOrder)).filter(
            agent_model.Agent.parentId == agent.parentId
        )
        result = await db.execute(stmt)
        max_order = result.scalar()
        # 如果文件夹为空(None)，则从 0 开始；否则在最大值基础上 +1
        agent.sortOrder = (max_order if max_order is not None else -1) + 1

    # agent_model 中的复杂字段已定义为 JSON，SQLAlchemy 会自动处理序列化
    agent_data = {k: v for k, v in agent.model_dump().items() if k in _AGENT_COLUMNS}

    db_agent = agent_model.Agent(**agent_data)
    db.add(db_agent)
    await db.commit()
    await db.refresh(db_agent)
    return db_agent


async def _find_sibling_by_name(db: AsyncSession, parent_id, name: str) -> Optional[agent_model.Agent]:
    """在同父目录下按名称查找节点（folder/agent 共享同名池子）。"""
    result = await db.execute(
        select(agent_model.Agent)
        .filter(agent_model.Agent.parentId == parent_id, agent_model.Agent.name == name)
        .limit(1)
    )
    return result.scalars().first()


async def update_agent(db: AsyncSession, agent_id: str, agent_update: schemas.AgentUpdate) -> Optional[
    agent_model.Agent]:
    """更新 Agent 或文件夹的配置信息"""
    db_agent = await get_agent(db, agent_id=agent_id)
    if not db_agent:
        return None

    update_data = agent_update.model_dump(exclude_unset=True)

    # 改名时检查：同父目录下其他节点不允许同名
    if "name" in update_data and update_data["name"] is not None \
            and update_data["name"] != db_agent.name:
        sibling = await _find_sibling_by_name(db, db_agent.parentId, update_data["name"])
        if sibling:
            raise ValueError(
                f"同目录下已存在同名节点: '{update_data['name']}'（{sibling.id[:8]}）。"
                "同一文件夹下名称必须唯一。"
            )

    if "subAgents" in update_data and update_data["subAgents"] is not None:
        has_cycle = await check_subagent_cycle(db, target_agent_id=agent_id, new_subagents=update_data["subAgents"])
        if has_cycle:
            raise ValueError("Circular dependency detected: An agent cannot have itself as a sub-agent (directly or indirectly).")
        if len(update_data["subAgents"]) > 0:
            agent_type = db_agent.AgentType
            atype = agent_type.value if hasattr(agent_type, 'value') else agent_type
            if atype not in (AgentTypeEnum.DEEP.value, AgentTypeEnum.MAMBO.value):
                raise ValueError("ReActAgent does not support sub-agents. Only DeepAgent or Mambo can mount sub-agents.")

            # 同名检查：所有子 Agent 共享同名池子
            sub_agents = await get_agents_by_ids(db, update_data["subAgents"])
            seen_names: dict[str, str] = {}
            for sub in sub_agents:
                if sub.name in seen_names:
                    raise ValueError(
                        f"Duplicate sub-agent name detected: '{sub.name}'. "
                        f"Sub-agents must have unique names."
                    )
                seen_names[sub.name] = sub.id

    # 仅更新实际 ORM 列，自动过滤掉 memoryResourceIds / securityReviewConfig 等转运字段
    for key in _AGENT_COLUMNS & update_data.keys():
        setattr(db_agent, key, update_data[key])

    await db.commit()
    await db.refresh(db_agent)
    return db_agent


async def delete_agent(db: AsyncSession, agent_id: str) -> Optional[agent_model.Agent]:
    """删除一个 Agent 或文件夹"""
    db_agent = await get_agent(db, agent_id=agent_id)
    if db_agent:
        await db.delete(db_agent)
        await db.commit()
    return db_agent


async def move_agents(db: AsyncSession, move_request: schemas.AgentMoveRequest) -> bool:
    """
    移动 Agent 或文件夹到指定位置（Inside, Before, After）。
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
        stmt = select(func.max(agent_model.Agent.sortOrder)).filter(agent_model.Agent.parentId == target_parent_id)
        result = await db.execute(stmt)
        max_order = result.scalar()
        target_sort_order = (max_order if max_order is not None else -1) + 1

    else:
        # Before 或 After，需要参考节点
        if move_request.reference_id == "root":
            return False

        ref_agent = await db.get(agent_model.Agent, move_request.reference_id)
        if not ref_agent:
            return False

        target_parent_id = ref_agent.parentId
        base_order = ref_agent.sortOrder

        if move_request.action == MoveAction.BEFORE:
            target_sort_order = base_order
        else:  # AFTER
            target_sort_order = base_order + 1

        # 2. 挤占位移：将插入点之后的同级节点 sortOrder 向后推
        shift_stmt = (
            update(agent_model.Agent)
            .where(agent_model.Agent.parentId == target_parent_id)
            .where(agent_model.Agent.sortOrder >= target_sort_order)
            .values(sortOrder=agent_model.Agent.sortOrder + len(move_request.item_ids))
        )
        await db.execute(shift_stmt)

    # 2.5 目标目录同名检查（与挤占位移同事务，冲突时回滚）
    await _check_move_name_conflict(db, move_request, target_parent_id)

    # 3. 更新被移动的节点
    # 保持 item_ids 原有的相对顺序
    for index, item_id in enumerate(move_request.item_ids):
        stmt = (
            update(agent_model.Agent)
            .where(agent_model.Agent.id == item_id)
            .values(
                parentId=target_parent_id,
                sortOrder=target_sort_order + index
            )
        )
        await db.execute(stmt)

    await db.commit()
    return True


async def _check_move_name_conflict(db: AsyncSession, move_request: schemas.AgentMoveRequest,
                                    target_parent_id) -> None:
    """移动前检查：目标目录内不允许出现同名节点（含被移动节点之间互查）。"""
    moving_ids = set(move_request.item_ids)
    result = await db.execute(
        select(agent_model.Agent.name)
        .filter(
            agent_model.Agent.parentId == target_parent_id,
            ~agent_model.Agent.id.in_(moving_ids),
        )
    )
    existing_names = set(result.scalars().all())
    for item_id in move_request.item_ids:
        item = await db.get(agent_model.Agent, item_id)
        if item is None:
            continue
        if item.name in existing_names:
            raise ValueError(
                f"目标目录已存在同名节点: '{item.name}'。同一文件夹下名称必须唯一。"
            )
        existing_names.add(item.name)


async def get_agents_by_ids(db: AsyncSession, agent_ids: List[str]) -> List[agent_model.Agent]:
    """通过ID列表批量获取 Agent"""
    if not agent_ids:
        return []
    result = await db.execute(
        select(agent_model.Agent).filter(agent_model.Agent.id.in_(agent_ids))
    )
    return list(result.scalars().all())