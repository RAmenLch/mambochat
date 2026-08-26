"""版本控制查询与恢复 API

提供历史文件内容查看和文件恢复，供前端 VersionHistoryDrawer 使用。
版本历史列表现在通过消息的 VERSION_SNAPSHOT submessage 展示，不再查询 BaseStore。
"""
from __future__ import annotations

import difflib
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal

from backend.schemas.version_control import (
    VersionFileContentResponse,
    DiffResponse,
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
    # 延迟导入：mambo_agents.middleware / backend.store 依赖较重，仅在版本历史功能使用时加载
    from backend.store import get_store as get_shared_store
    from mambo_agents.middleware.version_control import VersionStore
    return VersionStore(store=get_shared_store())


async def _build_restore_backend(db: AsyncSession, chat_id: str):
    """获取 chat 关联的 Agent 的 Backend（复用生成任务同一套构建逻辑）。

    Returns (backend, error_message). 成功时 error_message 为 None。
    """
    from backend.services.generation.agent.backend_factory import build_backend_from_chat_id
    from mambo_agents.backends.store import StoreBackend

    try:
        backend = await build_backend_from_chat_id(db, chat_id)
    except Exception as e:
        return None, str(e)

    # StoreBackend 依赖 graph config 中的 thread_id 做命名空间隔离。
    # 在 restore 上下文中没有 graph config，需显式注入 chat_id 作为 thread_id。
    if hasattr(backend, '_real') and isinstance(backend._real, StoreBackend):
        backend._real._thread_id = chat_id

    return backend, None


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


@router.get(
    "/versions/{chat_id}/diff/{path:path}",
    response_model=DiffResponse,
    summary="对比历史版本与当前文件的差异",
)
async def get_file_diff(
    chat_id: str,
    path: str,
    checkpoint_id: str = Query(..., description="目标 checkpoint ID"),
):
    # 延迟导入：mambo_agents.backends 依赖较重
    from mambo_agents.backends.schemas import VirtualPath

    store = _get_store()
    old_content = await store.aget_file(chat_id, checkpoint_id, f"/{path}")

    # 读取当前文件内容：先尝试 backend，失败则从 VersionStore 最新快照回退
    current_content: str | None = None
    read_error: str | None = None
    async with AsyncSessionLocal() as db:
        backend, build_err = await _build_restore_backend(db, chat_id)
    if backend is not None:
        try:
            r = await backend.aread_raw(VirtualPath(f"/{path}"), limit=None)
            if r.error:
                read_error = f"aread_raw error: {r.error.code} - {r.error.message}"
            else:
                current_content = r.content
        except Exception as e:
            read_error = f"aread_raw exception: {e}"
    else:
        read_error = f"build backend failed: {build_err}"

    # 回退：从 VersionStore 最新快照读取当前内容（StoreBackend 等场景兼容）
    if current_content is None:
        snapshots = await store.alist_snapshots(chat_id)
        for snap in reversed(snapshots):
            current_content = await store.aget_file(chat_id, snap.checkpoint_id, f"/{path}")
            if current_content is not None:
                break

    old_lines = (old_content or "").splitlines(keepends=True)
    cur_lines = (current_content or "").splitlines(keepends=True)

    diff_text = "".join(
        difflib.ndiff(old_lines, cur_lines)
    )

    return DiffResponse(
        path=f"/{path}",
        checkpoint_id=checkpoint_id,
        old_content=old_content,
        current_content=current_content,
        diff=diff_text,
        read_error=read_error,
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
        backend, err_msg = await _build_restore_backend(db, chat_id)

    if backend is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot build backend for restore: {err_msg}",
        )

    restored: list[str] = []
    errors: list[str] = []

    # 延迟导入：mambo_agents.backends 依赖较重
    from mambo_agents.backends.schemas import VirtualPath

    for file_path in file_list:
        content = await store.aget_file(chat_id, body.checkpoint_id, file_path)
        if content is None:
            errors.append(f"{file_path}: no content found at checkpoint")
            continue

        vp = VirtualPath(file_path)
        try:
            result = await backend.awrite(vp, content, overwrite=True)
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
