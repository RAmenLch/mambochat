# backend/services/generation/base.py
from abc import ABC, abstractmethod
import asyncio
import json
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple

from .llm_io import LLMInput, WorkerOutput
from .instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage,
    UpdateSubMessageStatus, SetFinalStatus
)
from ...models import chat_model
from ...schemas import enums as schemas_enums
from ...schemas import message as schemas_message
from ...services.stream_manager_service import stream_manager
from ...crud import message_crud, chat_crud, setting_crud


class AbstractGenerateWorker(ABC):
    """
    抽象生成工作者。
    负责将一个标准化的 LLMInput 转换为对特定 LLM API 的调用，
    并将响应流适配回标准化的 WorkerOutput 流。

    它是一个无状态的适配器，不应包含任何业务逻辑或数据库访问。
    """

    @abstractmethod
    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[WorkerOutput, None]:
        """
        与 LLM API 通信并生成标准化的输出流。

        Args:
            llm_input: 一个包含所有必要信息的标准化请求对象。

        Yields:
            WorkerOutput: 一系列标准化的输出块，供 Manager 消费。
        """
        if False:
            yield


class AbstractGenerateManager(ABC):
    """
    一个“框架式”的生成管理器。它处理所有通用流程，
    子类只需实现特定的业务逻辑。
    """

    def __init__(self, db_session: Any):
        self.db_session = db_session
        self.temp_ref_id_map: Dict[str, str] = {}

    # --- 抽象方法 (业务逻辑插槽) ---

    @abstractmethod
    async def _prepare_llm_input(
            self,
            db_chat: chat_model.Chat,
            history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        【业务逻辑插槽 1】
        将数据库对象转换为标准化的 LLM 输入。
        这是实现者定义“如何提问”的地方 (例如，构建 prompt)。
        """
        pass

    @abstractmethod
    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        【业务逻辑插槽 2】
        将 Worker 的标准输出翻译成具体的指令。
        这是实现者定义“如何处理回答”的地方。
        需要实现者自己管理状态（例如，是否已创建 sub-message）。
        """
        if False:
            yield

    @abstractmethod
    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus,
                                    exception: Optional[Exception] = None):
        """
        【业务逻辑插槽 3】
        定义在发生异常时如何清理，并可选择性地记录异常信息。
        """
        pass

    # --- 由基类提供的具体方法 (框架能力) ---

    async def _prepare_context(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> Tuple[chat_model.Chat, List[chat_model.Message]]:
        """
        【框架提供】
        准备生成所需的通用上下文（数据库对象）。
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
        【框架提供】
        处理一组标准的、通用的指令。
        """
        if isinstance(instruction, CreateSubMessage):
            config_data = schemas_message.SubMessageConfig(**(instruction.config or {}))
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
                    self.db_session, sub_message_id, instruction.content
                )
                await stream_manager.publish(
                    assistant_message_id,
                    {"type": "append", "sub_message_id": sub_message_id, "content": instruction.content}
                )
        elif isinstance(instruction, UpdateSubMessageStatus):
            sub_message_id = self.temp_ref_id_map.get(instruction.temp_ref_id)
            if sub_message_id:
                await message_crud.update_sub_message_status(
                    self.db_session, sub_message_id, instruction.status
                )
                await stream_manager.publish(
                    assistant_message_id,
                    {"type": "status_update", "sub_message_id": sub_message_id, "status": instruction.status.value}
                )
        elif isinstance(instruction, SetFinalStatus):
            return instruction.status
        else:
            return await self._process_custom_instruction(instruction, assistant_message_id)
        return None

    async def _process_custom_instruction(
            self,
            instruction: BaseInstruction,
            assistant_message_id: str
    ) -> Optional[schemas_enums.MessageStatus]:
        """
        【可选重写】
        一个空的“钩子”方法，用于处理非标准指令。
        """
        print(f"Warning: Unhandled custom instruction of type {type(instruction)}")
        return None

    # --- 模板方法 ---

    async def run(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> schemas_enums.MessageStatus:
        """
        模板方法：执行由工作者生成的指令流，并内置上下文准备、取消和错误处理逻辑。
        """
        overall_status = schemas_enums.MessageStatus.FAILED
        try:
            db_chat, history_messages = await self._prepare_context(chat_id, assistant_message_id)

            llm_input = await self._prepare_llm_input(db_chat, history_messages)

            worker_output_generator = worker.generate(llm_input)

            async for output in worker_output_generator:
                if await stream_manager.is_cancellation_requested(assistant_message_id):
                    raise asyncio.CancelledError("Generation was cancelled by user request.")

                instruction_generator = self._translate_worker_output_to_instructions(output)

                async for instruction in instruction_generator:
                    status_from_instruction = await self._process_instruction(instruction, assistant_message_id)
                    if status_from_instruction:
                        overall_status = status_from_instruction

        except (asyncio.CancelledError, Exception) as e:
            if isinstance(e, asyncio.CancelledError):
                print(f"[AbstractGenerateManager] Task cancelled for message '{assistant_message_id}'.")
                overall_status = schemas_enums.MessageStatus.COMPLETED
            else:
                print(
                    f"[AbstractGenerateManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
                overall_status = schemas_enums.MessageStatus.FAILED

            # 将异常传递给清理方法，以便在SubMessage中向用户显示
            await self._cleanup_on_exception(assistant_message_id, overall_status, e)

        return overall_status
