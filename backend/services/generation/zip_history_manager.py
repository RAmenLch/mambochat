# backend/services/generation/zip_history_manager.py
import json
from typing import AsyncGenerator, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.simple_manager import SimpleChatGenerateManager
from backend.services.generation.instructions import (
    BaseInstruction,
    UpdateZipHistorySubMessage,
    SetFinalStatus,
    UpdateSubMessageConfig
)
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.services.generation.default_manager import (
    _build_llm_messages_payload,
    _build_zip_history_messages_payload
)
from backend.crud import setting_crud, message_crud, chat_crud
from backend.models import chat_model
from backend.schemas import enums as schemas_enums
from backend.schemas import message as schemas_message
from backend.models.base_model import generate_uuid

DEFAULT_ZIP_HISTORY_PROMPT = (
    "你是一个对话历史压缩工具。请根据用户提供的对话历史，生成一段简洁、精确、信息完整的摘要。"
    "摘要应保留关键信息、问题、答案和上下文。请直接输出摘要文本，不要添加任何额外的解释或标题。"
)


class ZipHistoryGenerateManager(SimpleChatGenerateManager):
    """
    负责为对话历史生成压缩摘要的管理器。
    它准备一个特殊的LLM输入，请求模型生成摘要，然后将结果作为一种新的子消息类型附加到目标消息上。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.target_message_id: Optional[str] = None
        self._accumulated_content: str = ""
        self.chat_id: Optional[str] = None
        self.sub_message_id: Optional[str] = None  # 用于 ZipHistory 子消息的 ID

    async def _prepare_context(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> Tuple[chat_model.Chat, List[chat_model.Message]]:
        """
        重写基类方法，以准备用于压缩的特定历史消息范围。
        注意：这里的 assistant_message_id 实际上是 target_message_id。
        """
        db_chat = await chat_crud.get_chat(self.db_session, chat_id=chat_id)
        if not db_chat:
            raise ValueError(f"Chat with id {chat_id} not found.")

        # 获取所有消息用于切片
        all_messages = await message_crud.get_messages_by_chat(self.db_session, chat_id=chat_id)

        target_index = -1
        for i, msg in enumerate(all_messages):
            if msg.id == assistant_message_id:
                target_index = i
                break

        if target_index == -1:
            raise ValueError(f"Target message {assistant_message_id} not found in chat history.")

        # 仅使用目标消息（含）之前的消息作为上下文
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

        self.chat_id = db_chat.id
        provider = db_chat.ai_model.provider
        model = db_chat.ai_model

        # 1. 获取压缩任务的System Prompt
        prompt_setting = await setting_crud.get_setting(self.db_session, "zip_history_system_prompt")
        system_prompt = prompt_setting.value if prompt_setting and prompt_setting.value else DEFAULT_ZIP_HISTORY_PROMPT

        # 2. 使用共享函数构建消息负载
        effective_history = await _build_zip_history_messages_payload(history_messages)

        messages_payload = await _build_llm_messages_payload(
            self.db_session, effective_history, False
        )
        messages_payload.insert(0, {"role": "system", "content": system_prompt})
        messages_payload.append({"role": "user", "content": "请输出历史摘要:"})

        # 3. 准备模型参数和连接配置
        parameters = {'stream': False}
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
        覆盖 SimpleChatGenerateManager 的默认行为。
        """
        if output.type == "content" and output.content:
            self._accumulated_content += output.content

        elif output.type == "done":
            # 确保有 ID
            if not self.sub_message_id:
                self.sub_message_id = generate_uuid()

            yield UpdateZipHistorySubMessage(
                sub_message_id=self.sub_message_id,
                target_message_id=self.target_message_id,
                content=self._accumulated_content.strip(),
                status=schemas_enums.MessageStatus.COMPLETED
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            error_message = f"生成历史摘要时出错: {output.content}"
            if not self.sub_message_id:
                self.sub_message_id = generate_uuid()

            yield UpdateZipHistorySubMessage(
                sub_message_id=self.sub_message_id,
                target_message_id=self.target_message_id,
                content=error_message,
                status=schemas_enums.MessageStatus.FAILED
            )
            # 这里抛出异常以便触发清理逻辑或直接结束
            raise RuntimeError(error_message)

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        在发生未捕获的异常时，创建一个表示失败的ZipHistory子消息。
        """
        error_message = f"生成历史摘要时发生内部错误: {str(exception)}"

        # 确保有 ID
        if not self.sub_message_id:
            self.sub_message_id = generate_uuid()

        yield UpdateZipHistorySubMessage(
            sub_message_id=self.sub_message_id,
            target_message_id=assistant_message_id,
            content=error_message,
            status=schemas_enums.MessageStatus.FAILED
        )

    async def run(
            self,
            worker: 'AbstractGenerateWorker',
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        重写 run 方法。
        在开始生成前，先检查目标消息是否已启用压缩历史。
        如果是，发出指令将其禁用，并获取现有的 sub_message_id 以便进行更新而不是创建。
        """
        self.target_message_id = assistant_message_id

        target_message = await message_crud.get_message(self.db_session, assistant_message_id)
        if target_message:
            for sub in target_message.sub_messages:
                if sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
                    # 找到了现有的 ZipHistory
                    self.sub_message_id = sub.id

                    try:
                        config_obj = json.loads(sub.config) if isinstance(sub.config, str) else sub.config
                        # 仅当目标消息的压缩历史处于启用状态时，才将其禁用
                        # 这样做是为了防止上下文构建逻辑在遇到当前消息的压缩历史时停止回溯
                        if config_obj and config_obj.get('zip_enable') is True:
                            config_obj['zip_enable'] = False

                            # 发出指令更新配置
                            yield UpdateSubMessageConfig(
                                sub_message_id=sub.id,
                                config=config_obj
                            )
                            # 注意：Executor 执行此指令后，DB 更新完成。
                            # 随后调用的 super().run() -> _prepare_context 将能读取到更新后的状态。
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue

        # 执行基类的生成流程
        async for instruction in super().run(worker, chat_id, assistant_message_id):
            yield instruction

