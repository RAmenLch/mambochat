"""会话导出服务：按 doc/chat-export-spec.md 生成可导入的 JSON 包。"""

import base64
import json
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import chat_crud, message_crud, resource_crud
from backend.schemas.chat_export import (
    ChatExportPackage,
    ExportBlob,
    ExportChat,
    ExportFileRef,
    ExportMessage,
    ExportSubMessage,
)
from backend.schemas.enums import MessageStatus, ResourceType, SubMessageType
from backend.services.agent_package_service import MAMBOCHAT_VERSION
from backend.services.file_service import FileService
from backend.config.timezone_config import get_configured_now

EXPORT_FORMAT = "mambochat.chat-export"
EXPORT_FORMAT_VERSION = "1.3.0"

# 导出的子消息类型白名单（规范 §5.4）
EXPORT_SUB_TYPES = {
    SubMessageType.NORMAL.value,
    SubMessageType.REASONING.value,
    SubMessageType.MCP_TOOL.value,
    SubMessageType.USAGE.value,
    SubMessageType.ERROR.value,
    SubMessageType.TASK_SUBSTEP.value,
    SubMessageType.FILE.value,
}

# 中间态统一清洗为 failed（规范 §4.2）
_TRANSIENT_STATUS = {
    MessageStatus.GENERATING.value,
    MessageStatus.PENDING_REVIEW.value,
    MessageStatus.WAITING.value,
}


class ChatExporter:
    """将单个会话导出为 ChatExportPackage（活跃线性路径，含文件 blob）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    async def export(self, chat_id: str) -> ChatExportPackage:
        chat = await chat_crud.get_chat(self.db, chat_id)
        if chat is None or chat.itemType != 'chat':
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = await message_crud.get_messages_by_chat(self.db, chat_id)
        system_prompt = await self._build_system_prompt(chat)

        # 主查询已排除 TaskSubStep，导出需按规范补全（EXPORT_SUB_TYPES 含 TASK_SUBSTEP）
        task_subs = await message_crud.get_task_substeps_by_message_ids(
            self.db, [m.id for m in messages]
        )
        task_subs_by_msg: Dict[str, List] = {}
        for sub in task_subs:
            task_subs_by_msg.setdefault(sub.messageId, []).append(sub)

        blobs: Dict[str, ExportBlob] = {}
        export_messages: List[ExportMessage] = []
        for msg in messages:
            export_subs: List[ExportSubMessage] = []
            merged_subs = list(msg.sub_messages) + task_subs_by_msg.get(msg.id, [])
            merged_subs.sort(key=lambda s: (s.sortOrder, s.createdAt))
            for sub in merged_subs:
                if sub.type not in EXPORT_SUB_TYPES:
                    continue
                status = MessageStatus.FAILED.value if sub.status in _TRANSIENT_STATUS else sub.status
                config = self._parse_config(sub.config)

                content = sub.content
                file_ref = None
                if sub.type == SubMessageType.FILE.value:
                    blob = await self._collect_file_blob(sub.content, blobs)
                    if blob is None:
                        # 文件记录缺失（已被清理），跳过该子消息
                        continue
                    file_ref = ExportFileRef(
                        filename=blob.filename,
                        mimeType=blob.mimeType,
                        size=blob.size,
                        blobId=blob.blobId,
                    )
                    content = None

                export_subs.append(ExportSubMessage(
                    type=sub.type,
                    content=content,
                    config=config,
                    status=status,
                    sortOrder=sub.sortOrder,
                    createdAt=sub.createdAt,
                    file=file_ref,
                ))
            export_messages.append(ExportMessage(
                role=msg.role,
                createdAt=msg.createdAt,
                subMessages=export_subs,
            ))

        return ChatExportPackage(
            format=EXPORT_FORMAT,
            formatVersion=EXPORT_FORMAT_VERSION,
            mambochatVersion=MAMBOCHAT_VERSION,
            exportedAt=get_configured_now(),
            chat=ExportChat(
                name=chat.name,
                createdAt=chat.createdAt,
                chatMode=chat.chatMode or "normal",
                systemPrompt=system_prompt or None,
            ),
            messages=export_messages,
            blobs=list(blobs.values()),
        )

    async def _build_system_prompt(self, chat) -> str:
        """拼接会话自带 systemPrompt + system_prompt 资源 + submessage_template 资源（规范 §4.4）。"""
        base = chat.systemPrompt or ''
        resource_ids = chat.resource_prompt_list or []
        if not resource_ids:
            return base

        resources = await resource_crud.get_resources_by_ids(self.db, resource_ids)
        by_id = {r.id: r for r in resources}

        parts: List[str] = [base] if base else []
        for rid in resource_ids:
            res = by_id.get(rid)
            if res is None or res.latest_version is None:
                continue
            if res.resourceType not in (
                ResourceType.SYSTEM_PROMPT.value,
                ResourceType.SUBMESSAGE_TEMPLATE.value,
            ):
                continue
            content = res.latest_version.content
            if content:
                parts.append(content)
        return '\n\n'.join(parts).strip()

    async def _collect_file_blob(self, file_id: Optional[str], blobs: Dict[str, ExportBlob]) -> Optional[ExportBlob]:
        """按 File 记录去重收集 blob（规范 §4.3）；文件缺失返回 None。"""
        if not file_id:
            return None
        if file_id in blobs:
            return blobs[file_id]

        file = await self.file_service.get_file(file_id)
        if file is None:
            return None
        try:
            data = await self.file_service.get_file_content(file_id)
        except (HTTPException, FileNotFoundError):
            return None

        blob = ExportBlob(
            blobId=file.id,
            filename=file.filename,
            mimeType=file.mime_type,
            size=len(data),
            encoding='base64',
            data=base64.b64encode(data).decode('ascii'),
        )
        blobs[file.id] = blob
        return blob

    @staticmethod
    def _parse_config(config) -> Optional[dict]:
        if not config:
            return None
        if isinstance(config, str):
            try:
                return json.loads(config)
            except (json.JSONDecodeError, TypeError):
                return None
        return config if isinstance(config, dict) else None
