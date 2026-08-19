# backend/services/generation/agent/user_file_copy_service.py
"""用户消息文件副本写入服务。

Mambo Agent 会话中，用户发送的文件在消息创建时写入
/.mambo/chat_user_file/<file_id>.<ext>，并固化 file_copy_status 标志，
供 context_builder 在渲染文件信息时决定是否附加副本路径。

设计约束（缓存安全）：
- 副本只在消息创建时写入一次（幂等覆盖），不在请求构建时写；
- file_copy_status 创建时固化，永不翻转；失败不重试、不阻断发送/生成。
"""

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from mambo_agents.backends.schemas import VirtualPath

from backend.schemas import enums as schemas_enums
from backend.schemas.message import SubMessageConfig, SubMessageUpdate
from backend.crud import agent_crud, chat_crud, message_crud
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

# MIME -> 扩展名兜底映射（filename 无后缀时使用）
_MIME_EXT_FALLBACK = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/json": "json",
    "application/zip": "zip",
}


def derive_file_extension(filename: str, mime_type: str) -> str:
    """从 filename 后缀稳定推导扩展名；无后缀时按 mime 兜底，再无则省略。

    供副本写入与 context_builder 渲染副本路径共用，保证两端路径一致。
    """
    if filename:
        suffix = Path(filename).suffix
        if suffix:
            return suffix.lstrip(".").lower()
    return _MIME_EXT_FALLBACK.get(mime_type or "", "")


def _parse_config(raw: str | dict | None) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


async def process_user_message_files(
    db: AsyncSession,
    chat_id: str,
    message_id: str,
) -> None:
    """用户消息创建钩子：Mambo Agent 会话为文件生成 workspace 副本并固化标志位。

    - 非 Mambo Agent 会话直接返回（不设标志位）；
    - 副本写入失败不抛出：记录日志并固化 file_copy_status=failed，不阻断发送/生成。
    """
    # 1. 会话与 Agent 判定：仅 Mambo Agent 会话生效
    chat = await chat_crud.get_chat(db, chat_id)
    if not chat or chat.chatMode != schemas_enums.ChatMode.AGENT.value or not chat.agentId:
        return
    agent = await agent_crud.get_agent(db, chat.agentId)
    if not agent or agent.AgentType != schemas_enums.AgentTypeEnum.MAMBO.value:
        return

    # 2. 收集消息中的 FILE 子消息（仅限用户消息，需求 2）
    message = await message_crud.get_message(db, message_id)
    if not message or message.role != schemas_enums.MessageRole.USER.value:
        return
    file_subs = [
        sub for sub in message.sub_messages
        if sub.type == schemas_enums.SubMessageType.FILE.value
        and sub.status == schemas_enums.MessageStatus.COMPLETED.value
        and sub.content
    ]
    if not file_subs:
        return

    # 3. 构建 backend（显式 thread_id=chat_id，避免落到 __default__ namespace）
    try:
        from backend.services.generation.agent.backend_factory import (
            build_backend_from_chat_id,
        )

        backend = await build_backend_from_chat_id(db, chat_id, thread_id=chat_id)
    except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
        logger.warning(
            "[user_file_copy] 构建 backend 失败，跳过副本写入 chat=%s: %s", chat_id, e
        )
        return

    fs = FileService(db)
    for sub in file_subs:
        file_id = sub.content
        status = "failed"
        error: str | None = None
        try:
            db_file = await fs.get_file(file_id)
            if db_file is None:
                error = "file record not found"
            else:
                ext = derive_file_extension(db_file.filename, db_file.mime_type)
                raw = await fs.get_file_content(file_id)
                target = f"/.mambo/chat_user_file/{file_id}"
                if ext:
                    target += f".{ext}"
                results = await backend.aupload_files([(VirtualPath(target), raw)])
                if results and results[0].error is None:
                    status = "ok"
                else:
                    error = str(results[0].error) if results and results[0].error else "upload failed"
        except Exception as e:  # noqa: BLE001 - best-effort，失败不阻断
            error = f"{type(e).__name__}: {e}"
            logger.warning(
                "[user_file_copy] 副本写入异常 file=%s chat=%s: %s", file_id, chat_id, e
            )
        finally:
            await _set_copy_status(db, sub.id, status, error)


async def _set_copy_status(
    db: AsyncSession,
    sub_message_id: str,
    status: str,
    error: str | None,
) -> None:
    sub = await message_crud.get_sub_message(db, sub_message_id)
    if sub is None:
        return
    config = _parse_config(sub.config)
    config["file_copy_status"] = status
    if error:
        config["file_copy_error"] = error
    await message_crud.update_sub_message(
        db, sub_message_id, SubMessageUpdate(config=SubMessageConfig(**config))
    )
