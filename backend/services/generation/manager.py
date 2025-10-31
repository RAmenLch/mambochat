# backend/services/generation/manager.py
import json
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AbstractGenerateManager
from .instructions import (
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus,
    BaseInstruction
)
from ...crud import message_crud, chat_crud, setting_crud
from ...services.stream_manager_service import stream_manager
from ...schemas import message as schemas_message
from ...schemas import enums as schemas_enums
from ...models import chat_model


class DefaultGenerateManager(AbstractGenerateManager):
    """
    默认生成管理器。负责实现具体的上下文准备、指令处理和异常清理逻辑，
    继承自 AbstractGenerateManager 以复用流程控制。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)

    async def _prepare_context(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> Tuple[chat_model.Chat, List[chat_model.Message]]:
        """
        获取生成所需的会话对象和历史消息列表。
        """
        db_chat = await chat_crud.get_chat(self.db_session, chat_id=chat_id)
        if not db_chat:
            raise ValueError(f"Chat with id {chat_id} not found.")

        if not db_chat.aiModelId:
            default_model_setting = await setting_crud.get_setting(self.db_session, key="default_model_id")
            if default_model_setting and default_model_setting.value:
                db_chat.aiModelId = default_model_setting.value
                await self.db_session.commit()
                await self.db_session.refresh(db_chat)
                db_chat = await chat_crud.get_chat(self.db_session, chat_id=chat_id)
            else:
                raise ValueError("当前会话未指定模型，且未设置全局默认模型。")

        model_params = {}
        if db_chat.modelParameters:
            try:
                params_str = db_chat.modelParameters
                model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
            except (json.JSONDecodeError, TypeError):
                pass

        max_messages = model_params.get('max_context_messages')
        limit = max_messages if isinstance(max_messages, int) and max_messages > 0 else None

        if limit:
            history_messages = await message_crud.get_limited_recent_messages(self.db_session, chat_id=chat_id,
                                                                              limit=limit + 1)
            history_messages = [msg for msg in history_messages if msg.id != assistant_message_id]
            if len(history_messages) > limit:
                history_messages = history_messages[-limit:]
        else:
            all_messages = await message_crud.get_messages_by_chat(self.db_session, chat_id=chat_id)
            history_messages = [msg for msg in all_messages if msg.id != assistant_message_id]

        return db_chat, history_messages

    async def _process_instruction(
            self,
            instruction: BaseInstruction,
            assistant_message_id: str
    ) -> Optional[schemas_enums.MessageStatus]:
        """
        处理从工作者接收到的单个指令，并与数据库和流管理器交互。
        """
        if isinstance(instruction, CreateSubMessage):
            # 从指令的字典或None创建配置对象
            config_data = schemas_message.SubMessageConfig(
                **(instruction.config or {})
            )
            sub_message_create_schema = schemas_message.SubMessageCreate(
                content=instruction.initial_content,
                sortOrder=instruction.sortOrder,
                type=instruction.type,
                status=instruction.status,
                config=config_data
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
            return instruction.status

        return None

    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus):
        """
        在任务异常或被取消时，将所有仍处于'generating'状态的子消息更新为最终状态。
        """
        for temp_ref_id, sub_id in self.temp_ref_id_map.items():
            try:
                db_sub_message = await message_crud.get_sub_message(self.db_session, sub_id)
                if db_sub_message and db_sub_message.status == schemas_enums.MessageStatus.GENERATING.value:
                    await message_crud.update_sub_message_status(self.db_session, sub_id, final_status)
                    await stream_manager.publish(
                        assistant_message_id,
                        {"type": "status_update", "sub_message_id": sub_id, "status": final_status.value}
                    )
            except Exception as e_inner:
                print(f"[DefaultGenerateManager] Error updating sub-message {sub_id} during cleanup: {e_inner}")
