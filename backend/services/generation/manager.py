# backend/services/generation/manager.py
import json
from typing import AsyncGenerator, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AbstractGenerateManager
from .instructions import (
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus,
    BaseInstruction
)
from .llm_io import LLMInput, WorkerOutput
from ...services.stream_manager_service import stream_manager
from ...crud import message_crud, setting_crud
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
        self._main_content_started = False
        self._reasoning_content_started = False

    async def _prepare_llm_input(
        self,
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        根据会话配置和历史消息，准备发送给 Worker 的标准化 LLMInput。
        此函数包含根据 submessage 配置过滤上下文的核心逻辑。
        """
        if not db_chat.ai_model or not db_chat.ai_model.provider:
            raise ValueError("会话未配置有效的AI模型或服务商。")

        provider = db_chat.ai_model.provider
        model = db_chat.ai_model

        # 1. 将所有历史子消息扁平化处理
        flat_submessages = []
        for msg in history_messages:
            for sub in msg.sub_messages:
                flat_submessages.append((msg.role, sub))

        # 2. 根据 config 过滤子消息
        total_sub_count = len(flat_submessages)
        filtered_submessages = []
        for i, (role, sub) in enumerate(flat_submessages):
            pos_from_end = total_sub_count - i
            N = None
            if sub.config and isinstance(sub.config, str):
                try:
                    config_dict = json.loads(sub.config)
                    N = config_dict.get('context_participation_length')
                except (json.JSONDecodeError, TypeError):
                    pass
            elif sub.config and isinstance(sub.config, dict):
                N = sub.config.get('context_participation_length')

            if N is None or N > 0 and pos_from_end <= N:
                filtered_submessages.append((role, sub))

        # 3. 将过滤后的子消息重新聚合为 LLM API 的格式
        messages_payload = []
        if db_chat.systemPrompt:
            messages_payload.append({"role": "system", "content": db_chat.systemPrompt})

        if filtered_submessages:
            current_role = filtered_submessages[0][0]
            current_content_parts = [filtered_submessages[0][1].content]
            for i in range(1, len(filtered_submessages)):
                role, sub = filtered_submessages[i]
                if role == current_role:
                    current_content_parts.append(sub.content)
                else:
                    messages_payload.append({"role": current_role, "content": "\n".join(current_content_parts)})
                    current_role = role
                    current_content_parts = [sub.content]
            if current_content_parts:
                messages_payload.append({"role": current_role, "content": "\n".join(current_content_parts)})

        # 4. 准备模型参数和代理配置
        model_params = {}
        if db_chat.modelParameters:
            try:
                params_str = db_chat.modelParameters
                model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
            except (json.JSONDecodeError, TypeError):
                pass
        model_params.pop('max_context_messages', None)

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
            parameters=model_params,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url
        )

    async def _translate_worker_output_to_instructions(
        self,
        output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将 Worker 的标准输出翻译成具体的指令流。
        """
        if output.type == "reasoning":
            if not self._reasoning_content_started:
                yield CreateSubMessage(
                    temp_ref_id="reasoning_content", type="Reasoning", sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
                self._reasoning_content_started = True
            yield AppendToSubMessage(temp_ref_id="reasoning_content", content=output.content)

        elif output.type == "content":
            if not self._main_content_started:
                yield CreateSubMessage(
                    temp_ref_id="main_content", type="Normal", sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
                self._main_content_started = True
            yield AppendToSubMessage(temp_ref_id="main_content", content=output.content)

        elif output.type == "done":
            if self._main_content_started:
                yield UpdateSubMessageStatus(temp_ref_id="main_content", status=schemas_enums.MessageStatus.COMPLETED)
            if self._reasoning_content_started:
                yield UpdateSubMessageStatus(temp_ref_id="reasoning_content", status=schemas_enums.MessageStatus.COMPLETED)
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            error_message = f"\n\n**错误: {output.content}**"
            if not self._main_content_started and not self._reasoning_content_started:
                yield CreateSubMessage(
                    temp_ref_id="main_content", type="Normal", sortOrder=1,
                    status=schemas_enums.MessageStatus.FAILED, initial_content=f"生成失败: {output.content}"
                )
            else:
                if self._main_content_started:
                    yield AppendToSubMessage(temp_ref_id="main_content", content=error_message)
                    yield UpdateSubMessageStatus(temp_ref_id="main_content", status=schemas_enums.MessageStatus.FAILED)
                if self._reasoning_content_started:
                    yield UpdateSubMessageStatus(temp_ref_id="reasoning_content", status=schemas_enums.MessageStatus.FAILED)
            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)

    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus):
        """
        在任务异常或被取消时，将所有仍处于'generating'状态的子消息更新为最终状态。
        """
        if not self.temp_ref_id_map:
            try:
                sentinel_sub_message = schemas_message.SubMessageCreate(
                    content="", sortOrder=0, type="Normal", status=final_status,
                    config=schemas_message.SubMessageConfig()
                )
                db_sub_message = await message_crud.create_sub_message(
                    self.db_session, message_id=assistant_message_id, sub_message_data=sentinel_sub_message
                )
                stream_data = schemas_message.SubMessage.model_validate(db_sub_message).model_dump(mode='json')
                await stream_manager.publish(
                    assistant_message_id, {"type": "create", "sub_message": stream_data}
                )
            except Exception as e_inner:
                print(f"[DefaultGenerateManager] Error creating sentinel sub-message during cleanup: {e_inner}")
            return

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

