# backend/services/generation/manager.py
import asyncio
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AbstractGenerateManager, AbstractGenerateWorker
from .instructions import (
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus
)
from ...crud import message_crud
from ...services.stream_manager_service import stream_manager
from ...schemas import message as schemas_message
from ...schemas import enums as schemas_enums
from ...models import chat_model


class DefaultGenerateManager(AbstractGenerateManager):
    """
    默认生成管理器。负责接收并执行来自工作者的指令流，与数据库和流管理器交互。
    """
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.temp_ref_id_map: Dict[str, str] = {}

    async def run(
        self,
        worker: AbstractGenerateWorker,
        assistant_message_id: str,
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
    ) -> schemas_enums.MessageStatus:
        """
        执行由工作者生成的指令流。

        Args:
            worker: 负责生成指令的工作者实例。
            assistant_message_id: 当前正在生成的助手消息的ID。
            db_chat: 当前聊天会话的数据库对象。
            history_messages: 用于LLM上下文的历史消息列表。

        Returns:
            schemas_enums.MessageStatus: 整个生成任务的最终状态。
        """
        overall_status = schemas_enums.MessageStatus.FAILED
        try:
            async for instruction in worker.generate(
                db_chat=db_chat,
                history_messages=history_messages,
                assistant_message_id=assistant_message_id
            ):
                if isinstance(instruction, CreateSubMessage):
                    sub_message_create_schema = schemas_message.SubMessageCreate(
                        content=instruction.initial_content,
                        sortOrder=instruction.sortOrder,
                        type=instruction.type,
                        status=instruction.status
                    )
                    db_sub_message = await message_crud.create_sub_message(
                        self.db_session,
                        message_id=assistant_message_id,
                        sub_message_data=sub_message_create_schema
                    )
                    self.temp_ref_id_map[instruction.temp_ref_id] = db_sub_message.id

                    stream_data = schemas_message.SubMessage.model_validate(db_sub_message).model_dump(mode='json')
                    await stream_manager.publish(
                        assistant_message_id,
                        {"type": "create", "sub_message": stream_data}
                    )

                elif isinstance(instruction, AppendToSubMessage):
                    sub_message_id = self.temp_ref_id_map.get(instruction.temp_ref_id)
                    if sub_message_id:
                        await message_crud.append_to_sub_message_content(
                            self.db_session,
                            sub_message_id,
                            instruction.content
                        )
                        await stream_manager.publish(
                            assistant_message_id,
                            {"type": "append", "sub_message_id": sub_message_id, "content": instruction.content}
                        )

                elif isinstance(instruction, UpdateSubMessageStatus):
                    sub_message_id = self.temp_ref_id_map.get(instruction.temp_ref_id)
                    if sub_message_id:
                        await message_crud.update_sub_message_status(
                            self.db_session,
                            sub_message_id,
                            instruction.status
                        )
                        await stream_manager.publish(
                            assistant_message_id,
                            {"type": "status_update", "sub_message_id": sub_message_id, "status": instruction.status.value}
                        )
                elif isinstance(instruction, SetFinalStatus):
                    overall_status = instruction.status

        except asyncio.CancelledError:
            print(f"[GenerateManager] Task cancelled for message '{assistant_message_id}'.")
            overall_status = schemas_enums.MessageStatus.COMPLETED
            for temp_ref_id, sub_id in self.temp_ref_id_map.items():
                try:
                    db_sub_message = await message_crud.get_sub_message(self.db_session, sub_id)
                    if db_sub_message and db_sub_message.status == schemas_enums.MessageStatus.GENERATING.value:
                        await message_crud.update_sub_message_status(self.db_session, sub_id, schemas_enums.MessageStatus.COMPLETED)
                        await stream_manager.publish(
                            assistant_message_id,
                            {"type": "status_update", "sub_message_id": sub_id, "status": schemas_enums.MessageStatus.COMPLETED.value}
                        )
                except Exception as e:
                    print(f"[GenerateManager] Error updating sub-message {sub_id} on cancellation: {e}")

        except Exception as e:
            print(f"[GenerateManager] Unhandled error during instruction processing for message '{assistant_message_id}': {e}")
            overall_status = schemas_enums.MessageStatus.FAILED
            for temp_ref_id, sub_id in self.temp_ref_id_map.items():
                try:
                    db_sub_message = await message_crud.get_sub_message(self.db_session, sub_id)
                    if db_sub_message and db_sub_message.status == schemas_enums.MessageStatus.GENERATING.value:
                        await message_crud.update_sub_message_status(self.db_session, sub_id, schemas_enums.MessageStatus.FAILED)
                        await stream_manager.publish(
                            assistant_message_id,
                            {"type": "status_update", "sub_message_id": sub_id, "status": schemas_enums.MessageStatus.FAILED.value}
                        )
                except Exception as e_inner:
                    print(f"[GenerateManager] Error updating sub-message {sub_id} on error: {e_inner}")
        finally:
            return overall_status

