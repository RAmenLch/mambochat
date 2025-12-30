# backend/services/generation/instruction_executor.py

import json
import base64
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import message_crud, chat_crud, file_crud
from backend.services.stream_manager_service import stream_manager
from backend.services.storage_service import storage_service
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
    UpdateSubMessageConfig,
    SetFinalStatus,
    UpdateChatName,
    SaveAndPersistFile,
    UpdateZipHistorySubMessage,
    NotifyUser
)
from backend.routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID


class InstructionExecutor:
    """
    指令执行器。
    负责接收来自 Manager 的纯数据指令，执行相应的 IO 操作或数据库 CRUD 操作，
    并向 stream_manager 推送实时更新事件。
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def execute(
            self,
            instruction: BaseInstruction,
            chat_id: str,
            assistant_message_id: str
    ) -> Optional[schemas.enums.MessageStatus]:
        """
        执行单个指令。

        Args:
            instruction: 具体的指令对象。
            chat_id: 会话ID (用于通知或特定Chat级操作)。
            assistant_message_id: 关联的Assistant消息ID (用于流推送)。

        Returns:
            如果是 SetFinalStatus 指令，返回最终状态；否则返回 None。
        """

        if isinstance(instruction, CreateSubMessage):
            await self._execute_create_sub_message(instruction, assistant_message_id)

        elif isinstance(instruction, AppendToSubMessage):
            await self._execute_append_to_sub_message(instruction, assistant_message_id)

        elif isinstance(instruction, UpdateSubMessageContent):
            await self._execute_update_sub_message_content(instruction, assistant_message_id)

        elif isinstance(instruction, UpdateSubMessageStatus):
            await self._execute_update_sub_message_status(instruction, assistant_message_id)

        elif isinstance(instruction, UpdateSubMessageConfig):
            await self._execute_update_sub_message_config(instruction, assistant_message_id)

        elif isinstance(instruction, SaveAndPersistFile):
            await self._execute_save_and_persist_file(instruction)

        elif isinstance(instruction, UpdateChatName):
            await self._execute_update_chat_name(instruction)

        elif isinstance(instruction, UpdateZipHistorySubMessage):
            await self._execute_update_zip_history(instruction, chat_id, assistant_message_id)

        elif isinstance(instruction, NotifyUser):
            await self._execute_notify_user(instruction)

        elif isinstance(instruction, SetFinalStatus):
            return instruction.status

        else:
            print(f"[InstructionExecutor] Warning: Unhandled instruction type {type(instruction)}")

        return None

    async def _execute_create_sub_message(self, instruction: CreateSubMessage, assistant_message_id: str):
        # 转换配置字典
        config_data = schemas.message.SubMessageConfig(**(instruction.config or {}))

        sub_message_create_schema = schemas.message.SubMessageCreate(
            id=instruction.sub_message_id,  # 使用指令传入的预生成ID
            content=instruction.initial_content,
            sortOrder=instruction.sortOrder,
            type=instruction.type,
            status=instruction.status,
            config=config_data
        )

        # 调用 CRUD (注意：crud 需要适配支持传入 id)
        db_sub_message = await message_crud.create_sub_message(
            self.db_session,
            message_id=assistant_message_id,
            sub_message_data=sub_message_create_schema,
            sub_message_id=instruction.sub_message_id
        )

        # 推送流
        stream_data = schemas.message.SubMessage.model_validate(db_sub_message).model_dump(mode='json')
        await stream_manager.publish(
            assistant_message_id,
            {"type": "create", "sub_message": stream_data}
        )

    async def _execute_append_to_sub_message(self, instruction: AppendToSubMessage, assistant_message_id: str):
        await message_crud.append_to_sub_message_content(
            self.db_session, instruction.sub_message_id, instruction.content
        )
        await stream_manager.publish(
            assistant_message_id,
            {
                "type": "append",
                "sub_message_id": instruction.sub_message_id,
                "content": instruction.content
            }
        )

    async def _execute_update_sub_message_content(self, instruction: UpdateSubMessageContent,
                                                  assistant_message_id: str):
        await message_crud.update_sub_message(
            self.db_session,
            instruction.sub_message_id,
            schemas.message.SubMessageUpdate(content=instruction.content)
        )
        await stream_manager.publish(
            assistant_message_id,
            {
                "type": "content_update",
                "sub_message_id": instruction.sub_message_id,
                "content": instruction.content
            }
        )

    async def _execute_update_sub_message_status(self, instruction: UpdateSubMessageStatus, assistant_message_id: str):
        await message_crud.update_sub_message_status(
            self.db_session, instruction.sub_message_id, instruction.status
        )
        await stream_manager.publish(
            assistant_message_id,
            {
                "type": "status_update",
                "sub_message_id": instruction.sub_message_id,
                "status": instruction.status.value
            }
        )

    async def _execute_update_sub_message_config(self, instruction: UpdateSubMessageConfig, assistant_message_id: str):
        # 验证并转换 config
        try:
            config_obj = schemas.message.SubMessageConfig.model_validate(instruction.config)
            update_schema = schemas.message.SubMessageUpdate(config=config_obj)

            await message_crud.update_sub_message(
                self.db_session,
                instruction.sub_message_id,
                update_schema
            )

            # config 更新可能不频繁，也推送到流中以便前端响应
            await stream_manager.publish(
                assistant_message_id,
                {
                    "type": "config_update",
                    "sub_message_id": instruction.sub_message_id,
                    "config": instruction.config
                }
            )
        except Exception as e:
            print(f"[InstructionExecutor] Failed to update config for {instruction.sub_message_id}: {e}")

    async def _execute_save_and_persist_file(self, instruction: SaveAndPersistFile):
        """处理文件保存逻辑：解码 Base64 -> IO 存储 -> 数据库记录"""
        # 1. 解码 Base64 数据
        file_bytes = base64.b64decode(instruction.base64_data)
        size = len(file_bytes)

        # 2. 执行物理存储 IO
        # 如果此处发生异常，执行器会抛出异常中断流程，防止后续的 CreateSubMessage 被执行
        storage_path = await storage_service.save_from_bytes(
            data=file_bytes,
            filename=instruction.filename,
            sub_path="chat_attachments"
        )

        # 3. 创建数据库记录
        await file_crud.create_file(
            db=self.db_session,
            filename=instruction.filename,
            storage_path=storage_path,
            mime_type=instruction.mime_type,
            size=size,
            management_type=instruction.management_type,
            file_id=instruction.file_id  # 使用指令预生成的 ID
        )

    async def _execute_update_chat_name(self, instruction: UpdateChatName):
        await chat_crud.update_chat(
            self.db_session,
            chat_id=instruction.chat_id,
            chat_update=schemas.chat.ChatUpdate(name=instruction.new_name)
        )

        # 这是一个全局性更新，通过全局通知流广播
        notification_payload = {
            "type": "chat_update",
            "payload": {
                "id": instruction.chat_id,
                "name": instruction.new_name
            }
        }
        await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)

    async def _execute_update_zip_history(self, instruction: UpdateZipHistorySubMessage, chat_id: str,
                                          assistant_message_id: str):
        # 处理 ZipHistory 的特殊逻辑：存在则更新，不存在则创建
        existing = await message_crud.get_sub_message(self.db_session, instruction.sub_message_id)

        updated_sub_message = None
        if existing:
            update_schema = schemas.message.SubMessageUpdate(
                content=instruction.content,
                status=instruction.status
            )
            updated_sub_message = await message_crud.update_sub_message(
                self.db_session, instruction.sub_message_id, update_schema
            )
        else:
            create_schema = schemas.message.SubMessageCreate(
                id=instruction.sub_message_id,
                content=instruction.content,
                sortOrder=999,
                type=schemas.enums.SubMessageType.ZIP_HISTORY.value,
                status=instruction.status,
                config=schemas.message.SubMessageConfig(zip_enable=False, context_participation_length=0)
            )
            updated_sub_message = await message_crud.create_sub_message(
                self.db_session,
                message_id=instruction.target_message_id,
                sub_message_data=create_schema,
                sub_message_id=instruction.sub_message_id
            )

        if updated_sub_message:
            notification_payload = {
                "type": "zip_history_update",
                "payload": {
                    "chat_id": chat_id,
                    "message_id": instruction.target_message_id,
                    "sub_message": schemas.message.SubMessage.model_validate(updated_sub_message).model_dump(
                        mode='json')
                }
            }
            await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)

    async def _execute_notify_user(self, instruction: NotifyUser):
        """
        执行用户通知指令。
        将结构化的通知信息广播到全局通知流，供前端消费。
        """
        # serializes the generic BaseModel context to a dictionary
        context_data = instruction.context.model_dump(mode='json') if instruction.context else {}

        notification_payload = {
            "type": "notification",
            "category": instruction.category,
            "context": context_data,
            "level": instruction.level,
            "message": instruction.message
        }
        await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)

