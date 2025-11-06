# backend/services/generation/title_manager.py
import json
from typing import AsyncGenerator, List, Optional

from .base import AbstractGenerateManager
from .instructions import SetFinalStatus, UpdateChatName, BaseInstruction
from .llm_io import LLMInput, WorkerOutput
from ..stream_manager_service import stream_manager
from ...crud import setting_crud, provider_crud, chat_crud
from ...models import chat_model
from ... import schemas
from ...routers.notifications import GLOBAL_NOTIFICATIONS_STREAM_ID


class TitleGenerateManager(AbstractGenerateManager):
    """
    负责为会话自动生成标题的管理器。
    它准备一个特殊的LLM输入，请求模型生成标题，然后解析响应并更新会话名称。
    """

    def __init__(self, db_session):
        super().__init__(db_session)
        self.chat_id: Optional[str] = None
        self.error_occurred = False

    async def _prepare_llm_input(
        self,
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        准备用于生成标题的LLM输入。
        """
        self.chat_id = db_chat.id

        # 1. 获取标题生成模型ID，如果未设置则回退到全局默认模型
        model_id_to_use = None
        title_model_setting = await setting_crud.get_setting(self.db_session, "title_generation_model_id")
        if title_model_setting and title_model_setting.value:
            model_id_to_use = title_model_setting.value
        else:
            default_model_setting = await setting_crud.get_setting(self.db_session, "default_model_id")
            if default_model_setting and default_model_setting.value:
                model_id_to_use = default_model_setting.value

        if not model_id_to_use:
            raise ValueError("未配置标题生成模型, 且未设置全局默认模型作为备选。")

        # 2. 获取模型及其提供商信息
        model = await provider_crud.get_model(self.db_session, model_id=model_id_to_use)
        if not model or not model.provider:
            raise ValueError(f"用于生成标题的模型ID '{model_id_to_use}' 未找到或未关联提供商。")
        provider = model.provider

        # 3. 构建Prompt
        system_prompt = (
            "你是一个对话标题生成器。请根据以下对话内容, "
            "为其生成一个简洁、精确、不超过12个字的标题。"
            "请仅以JSON格式返回, 格式为: {\"title\": \"生成的标题\"}"
        )

        # 提取对话历史用于摘要
        context_messages = []
        if len(history_messages) <= 4:
            context_messages = history_messages
        else:
            context_messages.extend(history_messages[:2])
            context_messages.extend(history_messages[-2:])

        dialogue_summary = []
        for msg in context_messages:
            content = " ".join([sub.content[:200] for sub in msg.sub_messages])
            dialogue_summary.append(f"{msg.role}: {content}")

        user_content = "\n".join(dialogue_summary)

        messages_payload = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # 4. 准备模型参数和代理配置
        parameters = {
            'response_format': {'type': 'json_object'},
            'stream': False
        }

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
        将Worker的输出翻译成更新会话名称的指令。
        """
        if self.error_occurred:
            return

        if output.type == "content":
            try:
                data = json.loads(output.content)
                title = data.get("title")
                if isinstance(title, str) and 0 < len(title) <= 12:
                    yield UpdateChatName(chat_id=self.chat_id, new_name=title.strip())
                else:
                    self.error_occurred = True
                    print(f"[TitleGenerateManager] Invalid title format or length: {title}")
                    yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)
            except json.JSONDecodeError:
                self.error_occurred = True
                print(f"[TitleGenerateManager] Failed to decode JSON from LLM: {output.content}")
                yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

        elif output.type == "done":
            if not self.error_occurred:
                yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            self.error_occurred = True
            print(f"[TitleGenerateManager] Worker error: {output.content}")
            yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

    async def _process_custom_instruction(
        self,
        instruction: BaseInstruction,
        assistant_message_id: str
    ) -> Optional[schemas.enums.MessageStatus]:
        """
        处理自定义的 UpdateChatName 指令，并在成功后发布通知。
        """
        if isinstance(instruction, UpdateChatName):
            await chat_crud.update_chat(
                self.db_session,
                chat_id=instruction.chat_id,
                chat_update=schemas.ChatUpdate(name=instruction.new_name)
            )
            print(f"[TitleGenerateManager] Successfully updated chat '{instruction.chat_id}' name to '{instruction.new_name}'.")

            notification_payload = {
                "type": "chat_update",
                "payload": {
                    "id": instruction.chat_id,
                    "name": instruction.new_name
                }
            }
            await stream_manager.publish(GLOBAL_NOTIFICATIONS_STREAM_ID, notification_payload)

            return None
        return await super()._process_custom_instruction(instruction, assistant_message_id)

    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas.enums.MessageStatus):
        """
        此管理器不创建子消息，因此无需清理。
        """
        print(f"[TitleGenerateManager] Cleanup for task '{assistant_message_id}' with status {final_status.value}.")
        pass

