"""会话导入服务：按 doc/chat-export-spec.md 将导出包导入为新会话。"""

import base64
import json
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import chat_model
from backend.models.base_model import generate_uuid
from backend.models.file_model import File
from backend.schemas.chat_export import ChatExportPackage, ImportReport
from backend.schemas.enums import FileManagementType
from backend.services.agent_package_service import MAMBOCHAT_VERSION
from backend.services.storage_service import storage_service
from backend.utils.file_utils import FileUtils

EXPORT_FORMAT = "mambochat.chat-export"
EXPORT_FORMAT_VERSION = "1.3.0"
SUPPORTED_CHAT_MODES = {"normal", "agent"}

MAX_PACKAGE_SIZE = 100 * 1024 * 1024  # 100 MB（规范 §7.3）
MAX_BLOB_SIZE = 20 * 1024 * 1024      # 20 MB（规范 §7.3）

_CHAT_NAME_FALLBACK = "导入会话"
_CHAT_NAME_SUFFIX = " (导入)"
_MAX_CHAT_NAME = 90  # 预留后缀空间，保证最终名称 ≤ 100


def _version_tuple(v: str):
    parts = []
    for seg in str(v).split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts)


class ChatImporter:
    """将 ChatExportPackage 导入为新会话（单事务：失败整体回滚）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._written_physical_paths: List[str] = []

    async def do_import(self, pkg: ChatExportPackage) -> ImportReport:
        self._validate_package(pkg)
        blob_bytes = self._build_blob_index(pkg)

        name = await self._resolve_chat_name(pkg.chat.name)
        sort_order = await self._next_root_sort_order()

        new_chat = chat_model.Chat(
            name=name,
            itemType='chat',
            parentId=None,
            sortOrder=sort_order,
            systemPrompt=pkg.chat.systemPrompt,
            chatMode=pkg.chat.chatMode if pkg.chat.chatMode in SUPPORTED_CHAT_MODES else "normal",
        )
        self.db.add(new_chat)
        await self.db.flush()

        try:
            file_count = 0
            last_msg_id: Optional[str] = None
            for depth, msg in enumerate(pkg.messages):
                new_msg = chat_model.Message(
                    role=msg.role,
                    chatId=new_chat.id,
                    parentId=last_msg_id,
                    sortOrder=depth,
                    createdAt=msg.createdAt,
                    lastActiveAt=msg.createdAt,
                )
                self.db.add(new_msg)
                await self.db.flush()
                last_msg_id = new_msg.id

                for sub in msg.subMessages:
                    content = sub.content
                    if sub.file is not None:
                        data = blob_bytes.get(sub.file.blobId)
                        if data is None:
                            raise HTTPException(status_code=400, detail=f"Blob not found: {sub.file.blobId}")
                        content = await self._create_file_record(
                            generate_uuid(), data, sub.file.filename, sub.file.mimeType
                        )
                        file_count += 1

                    self.db.add(chat_model.SubMessage(
                        content=content or '',
                        messageId=new_msg.id,
                        sortOrder=sub.sortOrder,
                        type=sub.type,
                        config=json.dumps(sub.config, ensure_ascii=False) if sub.config else None,
                        status=sub.status,
                        createdAt=sub.createdAt,
                    ))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            await self._cleanup_physical_files()
            raise

        return ImportReport(
            chat_id=new_chat.id,
            name=name,
            message_count=len(pkg.messages),
            file_count=file_count,
        )

    # --- 校验与索引 ---

    def _validate_package(self, pkg: ChatExportPackage):
        if pkg.format != EXPORT_FORMAT:
            raise HTTPException(status_code=400, detail=f"格式错误：期望 {EXPORT_FORMAT}，实际 {pkg.format}")
        if _version_tuple(pkg.formatVersion) > _version_tuple(EXPORT_FORMAT_VERSION):
            raise HTTPException(
                status_code=400,
                detail=f"包格式版本 {pkg.formatVersion} 高于当前支持的 {EXPORT_FORMAT_VERSION}，请升级平台后再导入",
            )
        # mambochatVersion 低于当前版本仅警告，不阻断（规范 §7.1 步 2）
        if _version_tuple(pkg.mambochatVersion) < _version_tuple(MAMBOCHAT_VERSION):
            pass

    def _build_blob_index(self, pkg: ChatExportPackage) -> Dict[str, bytes]:
        index: Dict[str, bytes] = {}
        for blob in pkg.blobs:
            try:
                data = base64.b64decode(blob.data, validate=True)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"Blob {blob.blobId} 不是合法 base64")
            if len(data) > MAX_BLOB_SIZE:
                raise HTTPException(status_code=400, detail=f"Blob {blob.blobId} 超过单文件大小上限")
            if blob.size != len(data):
                raise HTTPException(status_code=400, detail=f"Blob {blob.blobId} 大小校验失败")
            index[blob.blobId] = data
        return index

    # --- 名称冲突（规范 §7.2）---

    async def _resolve_chat_name(self, name: Optional[str]) -> str:
        raw = (name or "").strip() or _CHAT_NAME_FALLBACK
        if len(raw) > _MAX_CHAT_NAME:
            raw = raw[:_MAX_CHAT_NAME]
        base = f"{raw}{_CHAT_NAME_SUFFIX}"
        n = 0
        while True:
            candidate = base if n == 0 else f"{base}_{n}"
            exists = await self.db.execute(
                select(chat_model.Chat.id).where(
                    chat_model.Chat.itemType == 'chat',
                    chat_model.Chat.parentId.is_(None),
                    chat_model.Chat.name == candidate,
                )
            )
            if exists.scalar() is None:
                return candidate
            n += 1

    async def _next_root_sort_order(self) -> int:
        result = await self.db.execute(
            select(func.max(chat_model.Chat.sortOrder)).where(chat_model.Chat.parentId.is_(None))
        )
        max_order = result.scalar()
        return (max_order if max_order is not None else -1) + 1

    # --- 文件落库（与 FileService.save_file_from_bytes 双引擎逻辑一致，但不提交，保持单事务）---

    async def _create_file_record(self, file_id: str, data: bytes, filename: str, mime_type: str) -> str:
        sample = data[:8192]
        final_mime = FileUtils.correct_mime_type(filename, mime_type, sample)
        if not FileUtils.is_allowed_mime_type(final_mime):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {final_mime}")

        size = len(data)
        if FileUtils.is_small_text_file(size, final_mime):
            try:
                text_content = FileUtils.decode_to_utf8(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            self.db.add(File(
                id=file_id,
                filename=filename,
                storage_path=f"virtual_db_{file_id}",
                mime_type=final_mime,
                size=size,
                storage_type='db',
                content=text_content,
                management_type=[FileManagementType.SUB_MESSAGE.value],
            ))
        else:
            try:
                storage_path = await storage_service.save_from_bytes(data, filename, "chat_attachments")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"文件存储失败: {e}")
            self._written_physical_paths.append(storage_path)
            self.db.add(File(
                id=file_id,
                filename=filename,
                storage_path=storage_path,
                mime_type=final_mime,
                size=size,
                storage_type='local',
                management_type=[FileManagementType.SUB_MESSAGE.value],
            ))
        return file_id

    async def _cleanup_physical_files(self):
        """事务回滚后删除本次写入的物理文件（DB 记录已随事务回滚）。"""
        for path in self._written_physical_paths:
            try:
                await storage_service.delete(path)
            except Exception:
                pass
