# backend/services/generation/zip_history_manager.py
import json
from typing import AsyncGenerator, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AbstractGenerateManager
from .instructions import BaseInstruction, UpdateZipHistorySubMessage, SetFinalStatus
from .llm_io import LLMInput, WorkerOutput
from .manager import _build_llm_messages_payload
from ..stream_manager_service import stream_manager
from ...crud import setting_crud, message_crud, chat_crud
from ...models import chat_model
from ...schemas import enums as schemas_enums
from ...schemas import message as schemas_message
from ...routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID

DEFAULT_ZIP_HISTORY_PROMPT = (
    "你是一个对话历史压缩工具。请根据用户提供的对话历史，生成一段简洁、精确、信息完整的摘要。"
    "摘要应保留关键信息、问题、答案和上下文。请直接输出摘要文本，不要添加任何额外的解释或标题。"
)


class ZipHistoryGenerateManager(AbstractGenerateManager):
    """
    负责为对话历史生成压缩摘要的管理器。
    它准备一个特殊的LLM输入，请求模型生成摘要，然后将结果作为一种新的子消息类型附加到目标消息上。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.target_message_id: Optional[str] = None
        self._accumulated_content: str = ""
        self.chat_id: Optional[str] = None

    async def _prepare_context(
        self,
        chat_id: str,
        target_message_id: str
    ) -> Tuple[chat_model.Chat, List[chat_model.Message]]:
        """
        重写基类方法，以准备用于压缩的特定历史消息范围。
        """
        db_chat = await chat_crud.get_chat(self.db_session, chat_id=chat_id)
        if not db_chat:
            raise ValueError(f"Chat with id {chat_id} not found.")

        all_messages = await message_crud.get_messages_by_chat(self.db_session, chat_id=chat_id)

        target_index = -1
        for i, msg in enumerate(all_messages):
            if msg.id == target_message_id:
                target_index = i
                break

        if target_index == -1:
            raise ValueError(f"Target message {target_message_id} not found in chat history.")

        messages_to_compress = all_messages[:target_index + 1]
        return db_chat, messages_to_compress

    async def _prepare_llm_input(
        self,
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        准备用于生成历史摘要的LLM输入。
        """
        if not db_chat.ai_model or not db_chat.ai_model.provider:
            raise ValueError("会话未配置有效的AI模型或服务商。")

        # 在 manager.run() 中，assistant_message_id 就是我们传入的 target_message_id
        self.target_message_id = self.temp_ref_id_map.get('__assistant_message_id__')
        self.chat_id = db_chat.id

        provider = db_chat.ai_model.provider
        model = db_chat.ai_model

        # 1. 获取压缩任务的System Prompt
        prompt_setting = await setting_crud.get_setting(self.db_session, "zip_history_system_prompt")
        system_prompt = prompt_setting.value if prompt_setting and prompt_setting.value else DEFAULT_ZIP_HISTORY_PROMPT

        # 2. 使用共享函数构建消息负载
        meta_config = json.loads(model.meta_config) if model.meta_config and isinstance(model.meta_config, str) else {}
        is_multimodal_enabled = 'image' in (meta_config.get('input_modalities') or [])
        messages_payload = await _build_llm_messages_payload(
            self.db_session, history_messages, is_multimodal_enabled
        )
        messages_payload.insert(0, {"role": "system", "content": system_prompt})
        messages_payload.append({"role": "user", "content": "请输出历史摘要:"})
        # 3. 准备模型参数和连接配置
        parameters = {'stream': True} # 强制流式以获得更好的体验
        proxy_url = None
        if provider.use_proxy:
            proxy_enabled_setting = await setting_crud.get_setting(self.db_session, "proxy_enabled")
            if proxy_enabled_setting and proxy_enabled_setting.value == 'True':
                proxy_url_setting = await setting_crud.get_setting(self.db_session, "proxy_url")
                if proxy_url_setting and proxy_url_setting.value:
                    proxy_url = proxy_url_setting.value

        return LLMInput(
            model_id=model.modelId,
            messages=messages_payload,
            parameters=parameters,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url
        )

    async def _translate_worker_output_to_instructions(
        self,
        output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将Worker的输出翻译成更新ZipHistory子消息的指令。
        """
        if output.type == "content" and output.content:
            self._accumulated_content += output.content

        elif output.type == "done":
            yield UpdateZipHistorySubMessage(
                target_message_id=self.target_message_id,
                content=self._accumulated_content.strip(),
                status=schemas_enums.MessageStatus.COMPLETED
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            error_message = f"生成历史摘要时出错: {output.content}"
            yield UpdateZipHistorySubMessage(
                target_message_id=self.target_message_id,
                content=error_message,
                status=schemas_enums.MessageStatus.FAILED
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)

    async def _process_custom_instruction(
        self,
        instruction: BaseInstruction,
        assistant_message_id: str
    ) -> Optional[schemas_enums.MessageStatus]:
        """
        处理自定义的 UpdateZipHistorySubMessage 指令，并发布全局通知。
        """
        if isinstance(instruction, UpdateZipHistorySubMessage):
            target_message = await message_crud.get_message(self.db_session, instruction.target_message_id)
            if not target_message:
                print(f"[ZipHistoryManager] Target message {instruction.target_message_id} not found. Cannot update zip history.")
                return

            existing_sub_message = None
            for sub in target_message.sub_messages:
                if sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
                    existing_sub_message = sub
                    break

            updated_sub_message = None
            if existing_sub_message:
                update_schema = schemas_message.SubMessageUpdate(
                    content=instruction.content,
                    status=instruction.status
                )
                updated_sub_message = await message_crud.update_sub_message(
                    self.db_session, existing_sub_message.id, update_schema
                )
            else:
                create_schema = schemas_message.SubMessageCreate(
                    content=instruction.content,
                    sortOrder=999, # 确保在末尾
                    type=schemas_enums.SubMessageType.ZIP_HISTORY.value,
                    status=instruction.status,
                    config=schemas_message.SubMessageConfig(zip_enable=False, context_participation_length=0)
                )
                updated_sub_message = await message_crud.create_sub_message(
                    self.db_session, instruction.target_message_id, create_schema
                )

            # 发布通知，告知前端压缩任务已完成
            if updated_sub_message:
                notification_payload = {
                    "type": "zip_history_update",
                    "payload": {
                        "chat_id": self.chat_id,
                        "message_id": instruction.target_message_id,
                        "sub_message": schemas_message.SubMessage.model_validate(updated_sub_message).model_dump(mode='json')
                    }
                }
                await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)

            return None # 不影响最终状态
        return await super()._process_custom_instruction(instruction, assistant_message_id)

    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus,
                                    exception: Optional[Exception] = None):
        """
        在发生未捕获的异常时，创建一个表示失败的ZipHistory子消息。
        """
        error_message = f"生成历史摘要时发生内部错误: {str(exception)}"
        fail_instruction = UpdateZipHistorySubMessage(
            target_message_id=assistant_message_id,
            content=error_message,
            status=schemas_enums.MessageStatus.FAILED
        )
        await self._process_custom_instruction(fail_instruction, assistant_message_id)

    async def run(
            self,
            worker: 'AbstractGenerateWorker',
            chat_id: str,
            assistant_message_id: str
    ) -> schemas_enums.MessageStatus:
        """
        重写run方法以在内部传递 target_message_id。
        """
        self.temp_ref_id_map['__assistant_message_id__'] = assistant_message_id
        return await super().run(worker, chat_id, assistant_message_id)
