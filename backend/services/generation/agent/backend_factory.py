"""Backend 构建公用函数。

从 Agent ORM 对象或 chat_id 重建 BackendProtocol，
复用于生成任务构建和 pending file SSE handler 等独立场景。
"""

from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from mambo_agents import BackendProtocol

from backend.models.agent_model import Agent
from backend.schemas.enums import ResourceType
from backend.crud import backend_crud, resource_crud


async def build_mounted_backends(
    db: AsyncSession, agent: Agent
) -> list[dict[str, Any]]:
    """从 Agent.backendIds 构建 mounted_backends 列表（与 initializer 逻辑一致）。"""
    mounted: list[dict[str, Any]] = []
    if agent.backendIds:
        backends_db = await backend_crud.get_backends_by_ids(db, agent.backendIds)
        for b in backends_db:
            config_data = dict(b.configData) if b.configData else {}
            if b.tools_config:
                config_data["tools_config"] = b.tools_config
            mounted.append({
                "id": b.id,
                "name": b.name,
                "backendType": b.backendType,
                "configData": config_data,
            })
    return mounted


async def build_skill_resource_roots(
    db: AsyncSession, agent: Agent
) -> dict[str, str]:
    """从 agent.resourcePromptList 提取 SKILL 类型资源映射。"""
    if not agent.resourcePromptList:
        return {}
    roots: dict[str, str] = {}
    for rid in agent.resourcePromptList:
        res = await resource_crud.get_resource(db, rid)
        if res is None or res.resourceType != ResourceType.SKILL.value:
            continue
        roots[res.name] = res.id
    return roots


async def build_backend_from_chat_id(
    db: AsyncSession, chat_id: str,
) -> BackendProtocol:
    """从 chat_id 反查 agent，重建与生成任务相同的 BackendProtocol。

    用于 pending file SSE handler 等独立于生成任务生命周期的场景。
    """
    from backend.crud import chat_crud, agent_crud
    from backend.services.generation.graph_builders.mambo_agent_builder import (
        _build_mambo_backend,
    )
    from backend.services.generation.core.llm_io import AgentConfig
    from backend.store import get_store

    chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not chat or not chat.agentId:
        raise ValueError(f"Chat {chat_id} has no agent configured")

    agent = await agent_crud.get_agent(db, chat.agentId)
    if not agent:
        raise ValueError(f"Agent {chat.agentId} not found")

    mounted_backends = await build_mounted_backends(db, agent)
    skill_roots = await build_skill_resource_roots(db, agent)

    agent_config = AgentConfig(
        mounted_backends=mounted_backends if mounted_backends else None,
        default_backend_id=agent.defaultBackendId,
        skill_resource_roots=skill_roots if skill_roots else None,
        memory_resource_roots=None,
    )

    store = get_store()
    return _build_mambo_backend(agent_config, store=store)
