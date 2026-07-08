"""版本控制查询与恢复 API

提供历史文件内容查看和文件恢复，供前端 VersionHistoryDrawer 使用。
版本历史列表现在通过消息的 VERSION_SNAPSHOT submessage 展示，不再查询 BaseStore。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mambo_agents.backends.schemas import VirtualPath
from mambo_agents.backends.ssh import SshBackend
from mambo_agents.middleware.version_control import VersionStore

from backend.crud import backend_crud
from backend.database import AsyncSessionLocal
from backend.models import chat_model, agent_model
from backend.store import get_store as get_shared_store

from backend.schemas.version_control import (
    VersionFileContentResponse,
)
from backend.schemas.message import (
    VersionSnapshotContent,
    RollbackRecord,
    SubMessageCreate,
    SubMessageConfig,
)
from backend.schemas.enums import SubMessageType, MessageStatus
from backend.crud import message_crud
from backend.models.base_model import generate_uuid

router = APIRouter()


# ──────────────────────────── Restore Schema ────────────────────────────

class RestoreRequest(BaseModel):
    """文件恢复请求"""
    checkpoint_id: str = Field(..., description="目标 checkpoint ID")
    files: list[str] = Field(default_factory=list, description="要恢复的文件路径列表")


class RestoreResponse(BaseModel):
    """文件恢复结果"""
    success: bool = True
    restored: list[str] = Field(default_factory=list, description="成功恢复的文件路径")
    errors: list[str] = Field(default_factory=list, description="失败的文件及原因")


# ──────────────────────────── Helpers ────────────────────────────


def _get_store() -> VersionStore:
    return VersionStore(store=get_shared_store())


def _make_session_factory() -> Any:
    """创建异步 session 工厂，与 builder 中的逻辑一致"""
    from backend.database import AsyncSessionLocal
    return lambda: AsyncSessionLocal()


async def _build_restore_backend(db: AsyncSession, chat_id: str) -> Optional[Any]:
    """获取 chat 关联的 Agent 默认 Backend 并构建实例。
    
    仅支持 Resource 和 SSH 类型 backend 的恢复写入。
    """
    # 1. 查找 chat
    result = await db.execute(
        select(chat_model.Chat).filter(chat_model.Chat.id == chat_id)
    )
    chat = result.scalars().first()
    if chat is None:
        return None

    # 2. 查找 agent
    if not chat.agentId:
        return None
    result = await db.execute(
        select(agent_model.Agent).filter(agent_model.Agent.id == chat.agentId)
    )
    agent = result.scalars().first()
    if agent is None:
        return None

    # 3. 获取默认 backend
    default_bid = agent.defaultBackendId
    if not default_bid:
        return None
    backend_cfg = await backend_crud.get_backend(db, default_bid)
    if backend_cfg is None:
        return None

    # 4. 构建 backend 实例
    b_type = backend_cfg.backendType
    config = dict(backend_cfg.configData) if backend_cfg.configData else {}

    if b_type == "resource":
        from backend.services.generation.agent.mambo_resource_backend import MamboResourceBackend

        resource_id = config.get("resource_id", "")
        if not resource_id:
            return None
        return MamboResourceBackend(
            resource_id=resource_id,
            session_factory=_make_session_factory(),
            workspace_root=VirtualPath("/workspace"),
        )

    elif b_type == "ssh":
        from backend.utils.ssh_utils import get_or_create_system_ssh_key

        priv_key_path = None
        if not config.get("password"):
            priv_key_path, _ = get_or_create_system_ssh_key()

        return SshBackend(
            host=config.get("hostname", ""),
            port=config.get("port", 22),
            username=config.get("username", ""),
            password=config.get("password"),
            key_filename=priv_key_path,
            remote_root=config.get("root_dir", "~"),
        )

    elif b_type == "api":
        from backend.services.generation.agent.mambo_api_backend import MamboAPIBackend

        return MamboAPIBackend(
            backend_id=backend_cfg.id,
            backend_name=backend_cfg.name,
        )

    return None


# ──────────────────────────── API Endpoints ────────────────────────────


@router.get(
    "/versions/{chat_id}/files/{path:path}",
    response_model=VersionFileContentResponse,
    summary="获取指定版本的文件内容",
)
async def get_file_version(
    chat_id: str,
    path: str,
    checkpoint_id: str = Query(..., description="目标 checkpoint ID"),
):
    store = _get_store()
    content = await store.aget_file(chat_id, checkpoint_id, f"/{path}")
    sha = None
    if content is not None:
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return VersionFileContentResponse(
        path=f"/{path}",
        checkpoint_id=checkpoint_id,
        content=content,
        sha256=sha,
    )


@router.post(
    "/versions/{chat_id}/restore",
    response_model=RestoreResponse,
    summary="将指定文件恢复到历史版本",
)
async def restore_files(chat_id: str, body: RestoreRequest):
    """读取 VersionStore 中的历史文件内容，通过 Agent 的默认 Backend 写回。"""
    store = _get_store()

    # 如果 files 为空，获取该快照的所有变更文件
    file_list = body.files
    if not file_list:
        file_list = await store.aget_changed_files(chat_id, body.checkpoint_id)

    if not file_list:
        raise HTTPException(status_code=400, detail="No files to restore")

    # 构建 backend
    async with AsyncSessionLocal() as db:
        backend = await _build_restore_backend(db, chat_id)

    if backend is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot build backend for restore. Ensure the Agent has a default backend (Resource/SSH/API).",
        )

    restored: list[str] = []
    errors: list[str] = []

    for file_path in file_list:
        content = await store.aget_file(chat_id, body.checkpoint_id, file_path)
        if content is None:
            errors.append(f"{file_path}: no content found at checkpoint")
            continue

        vp = VirtualPath(file_path)
        try:
            result = backend.write(vp, content, overwrite=True)
            if hasattr(result, 'error') and result.error:
                errors.append(f"{file_path}: {result.error}")
            else:
                restored.append(file_path)
        except Exception as e:
            errors.append(f"{file_path}: {e}")

    # 写入回滚记录到最近 assistant 消息
    async with AsyncSessionLocal() as db:
        messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        last_assistant = next(
            (m for m in reversed(messages) if hasattr(m, 'role') and str(m.role) == 'assistant'),
            None,
        )
        if last_assistant:
            rollback = RollbackRecord(
                target_checkpoint_id=body.checkpoint_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                restored=restored,
                errors=errors,
            )
            snapshot = VersionSnapshotContent(
                checkpoint_id=body.checkpoint_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                files=[],
                rollback=rollback,
            )
            sub = SubMessageCreate(
                id=generate_uuid(),
                type=SubMessageType.VERSION_SNAPSHOT,
                sortOrder=50,
                status=MessageStatus.COMPLETED,
                content=snapshot.to_json_string(),
                config=SubMessageConfig(context_participation_length=0),
            )
            await message_crud.create_sub_message(db, last_assistant.id, sub)
            await db.commit()

    return RestoreResponse(
        success=len(restored) > 0,
        restored=restored,
        errors=errors,
    )
