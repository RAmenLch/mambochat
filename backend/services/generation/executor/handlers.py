# backend/services/generation/executor/handlers.py

import json
import base64
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import message_crud, chat_crud
from backend.services.stream_manager_service import stream_manager
from backend.services.file_service import FileService
from backend.routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID

# 导入核心层的指令定义
from backend.services.generation.core.instructions import (
    CreateSubMessage, AppendToSubMessage, UpdateSubMessageContent,
    UpdateSubMessageStatus, UpdateSubMessageConfig, SetFinalStatus,
    UpdateChatName, SaveAndPersistFile, UpdateZipHistorySubMessage, NotifyUser,
    FailSubMessagesByMessage, SetMessageCheckpointId
)
from backend.crud import checkpoint_map_crud


async def handle_create_sub_message(
    instruction: CreateSubMessage, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    config_data = schemas.message.SubMessageConfig(**(instruction.config or {}))
    sub_message_create_schema = schemas.message.SubMessageCreate(
        id=instruction.sub_message_id,
        content=instruction.initial_content,
        sortOrder=instruction.sortOrder,
        type=instruction.type,
        status=instruction.status,
        config=config_data
    )

    db_sub_message = await message_crud.create_sub_message(
        db,
        message_id=assistant_message_id,
        sub_message_data=sub_message_create_schema,
        sub_message_id=instruction.sub_message_id
    )

    stream_data = schemas.message.SubMessage.model_validate(db_sub_message).model_dump(mode='json')
    await stream_manager.publish(
        assistant_message_id,
        {"type": "create", "sub_message": stream_data}
    )


async def handle_append_to_sub_message(
    instruction: AppendToSubMessage, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    await message_crud.append_to_sub_message_content(db, instruction.sub_message_id, instruction.content)
    await stream_manager.publish(
        assistant_message_id,
        {
            "type": "append",
            "sub_message_id": instruction.sub_message_id,
            "content": instruction.content
        }
    )


async def handle_update_sub_message_content(
    instruction: UpdateSubMessageContent, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    await message_crud.update_sub_message(
        db, instruction.sub_message_id, schemas.message.SubMessageUpdate(content=instruction.content)
    )
    await stream_manager.publish(
        assistant_message_id,
        {
            "type": "content_update",
            "sub_message_id": instruction.sub_message_id,
            "content": instruction.content
        }
    )


async def handle_update_sub_message_status(
    instruction: UpdateSubMessageStatus, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    await message_crud.update_sub_message_status(db, instruction.sub_message_id, instruction.status)
    await stream_manager.publish(
        assistant_message_id,
        {
            "type": "status_update",
            "sub_message_id": instruction.sub_message_id,
            "status": instruction.status.value
        }
    )


async def handle_update_sub_message_config(
    instruction: UpdateSubMessageConfig, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    db_sub_message = await message_crud.get_sub_message(db, instruction.sub_message_id)
    if not db_sub_message:
        print(f"[InstructionExecutor] SubMessage {instruction.sub_message_id} not found for config update.")
        return

    try:
        current_config = {}
        if db_sub_message.config:
            try:
                current_config = json.loads(db_sub_message.config)
            except (json.JSONDecodeError, TypeError):
                current_config = {}

        merged_config = {**current_config, **instruction.config}
        config_obj = schemas.message.SubMessageConfig.model_validate(merged_config)
        update_schema = schemas.message.SubMessageUpdate(config=config_obj)

        await message_crud.update_sub_message(db, instruction.sub_message_id, update_schema)

        await stream_manager.publish(
            assistant_message_id,
            {
                "type": "config_update",
                "sub_message_id": instruction.sub_message_id,
                "config": config_obj.model_dump(mode='json')
            }
        )
    except Exception as e:
        print(f"[InstructionExecutor] Failed to update config for {instruction.sub_message_id}: {e}")


async def handle_save_and_persist_file(
    instruction: SaveAndPersistFile, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    file_bytes = base64.b64decode(instruction.base64_data)
    file_service = FileService(db)
    await file_service.save_file_from_bytes(
        data=file_bytes,
        filename=instruction.filename,
        mime_type=instruction.mime_type,
        management_type=[instruction.management_type],
        sub_path="chat_attachments",
        file_id=instruction.file_id
    )


async def handle_update_chat_name(
    instruction: UpdateChatName, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    await chat_crud.update_chat(
        db, chat_id=instruction.chat_id, chat_update=schemas.chat.ChatUpdate(name=instruction.new_name)
    )
    notification_payload = {
        "type": "chat_update",
        "payload": {"id": instruction.chat_id, "name": instruction.new_name}
    }
    await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)


async def handle_update_zip_history(
    instruction: UpdateZipHistorySubMessage, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    # 确保同一个 message 最多只有一个 ZipHistory：先删除该 message 下所有旧的 ZipHistory
    # （排除当前 sub_message_id，因为 Manager 复用已有 ID 重压缩时不应删掉自己）
    await message_crud.delete_zip_history_by_message_id(
        db,
        message_id=instruction.target_message_id,
        exclude_id=instruction.sub_message_id,
    )

    existing = await message_crud.get_sub_message(db, instruction.sub_message_id)

    # 构建 config，包含 zip_enable 和 target_sub_msg_id（如果有）
    config_kwargs = {
        "zip_enable": instruction.zip_enable,
        "context_participation_length": 0,
    }
    if instruction.target_sub_msg_id:
        config_kwargs["target_sub_msg_id"] = instruction.target_sub_msg_id

    updated_sub_message = None
    if existing:
        update_schema = schemas.message.SubMessageUpdate(
            content=instruction.content,
            status=instruction.status,
            config=schemas.message.SubMessageConfig(**config_kwargs),
        )
        updated_sub_message = await message_crud.update_sub_message(db, instruction.sub_message_id, update_schema)
    else:
        create_schema = schemas.message.SubMessageCreate(
            id=instruction.sub_message_id,
            content=instruction.content,
            sortOrder=999,
            type=schemas.enums.SubMessageType.ZIP_HISTORY.value,
            status=instruction.status,
            config=schemas.message.SubMessageConfig(**config_kwargs)
        )
        updated_sub_message = await message_crud.create_sub_message(
            db, message_id=instruction.target_message_id, sub_message_data=create_schema, sub_message_id=instruction.sub_message_id
        )

    if updated_sub_message:
        notification_payload = {
            "type": "zip_history_update",
            "payload": {
                "chat_id": chat_id,
                "message_id": instruction.target_message_id,
                "sub_message": schemas.message.SubMessage.model_validate(updated_sub_message).model_dump(mode='json')
            }
        }
        await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)


async def handle_notify_user(
    instruction: NotifyUser, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    context_data = instruction.context.model_dump(mode='json') if instruction.context else {}
    notification_payload = {
        "type": "notification",
        "category": instruction.category,
        "context": context_data,
        "level": instruction.level,
        "message": instruction.message
    }
    await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)


async def handle_fail_sub_messages_by_message(
    instruction: FailSubMessagesByMessage, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    """
    将指定消息下所有 GENERATING 状态的子消息批量标记为 FAILED，
    并对 Reasoning 类型子消息设置 is_minimal=True。
    通过 SSE 推送每条子消息的状态更新。
    """
    from sqlalchemy import update as sa_update
    from backend.models.chat_model import SubMessage as SubMessageModel

    target_status = instruction.status

    # 1. 查询所有 GENERATING 的子消息
    stmt = (
        sa_update(SubMessageModel)
        .where(SubMessageModel.messageId == instruction.message_id)
        .where(SubMessageModel.status == schemas.enums.MessageStatus.GENERATING.value)
        .values(status=target_status.value)
    )
    result = await db.execute(stmt)
    await db.commit()

    # 2. 查询受影响的 Reasoning 类型子消息，设置 is_minimal=True
    stmt_reasoning = (
        sa_update(SubMessageModel)
        .where(SubMessageModel.messageId == instruction.message_id)
        .where(SubMessageModel.type == schemas.enums.SubMessageType.REASONING.value)
        .where(SubMessageModel.status == target_status.value)
        .values(config=json.dumps({"is_minimal": True}))
    )
    await db.execute(stmt_reasoning)
    await db.commit()

    # 3. 推送 SSE 通知（汇总一条消息，前端据此刷新子消息状态）
    await stream_manager.publish(
        instruction.message_id,
        {
            "type": "batch_status_update",
            "message_id": instruction.message_id,
            "status": target_status.value
        }
    )


async def handle_set_final_status(
    instruction: SetFinalStatus, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> schemas.enums.MessageStatus:
    """这是一个特殊的指令，它不操作数据库，而是直接向外层返回最终的状态枚举"""
    return instruction.status


async def handle_set_message_checkpoint_id(
    instruction: SetMessageCheckpointId, chat_id: str, assistant_message_id: str, db: AsyncSession
) -> None:
    """将 message_id ↔ checkpoint_id 映射写入 message_checkpoints_map 表。"""
    await checkpoint_map_crud.set_checkpoint_id(
        db, instruction.message_id, instruction.checkpoint_id, chat_id
    )
