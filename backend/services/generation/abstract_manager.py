# backend/services/generation/abstract_manager.py
import asyncio
import json
import traceback
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Tuple, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.instructions import BaseInstruction
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.models import chat_model
from backend.crud import chat_crud, message_crud
from backend.schemas import enums as schemas_enums
from backend.services.stream_manager_service import stream_manager


class AbstractGenerateManager(ABC):
    """
    一个“框架式”的生成管理器。它处理所有通用流程，
    子类只需实现特定的业务逻辑。
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

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
        需要实现者自己管理状态（例如，SubMessage ID 的生成与映射）。
        """
        if False:
            yield

    @abstractmethod
    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        【业务逻辑插槽 3】
        定义在发生异常时如何清理。
        返回一个指令流，用于更新状态或创建错误消息。
        """
        if False:
            yield

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

        # 如果会话未配置模型，抛出错误。
        # 补全默认模型的逻辑已移至 Service 层处理，此处仅做校验。
        if not db_chat.aiModelId:
            raise ValueError("当前会话未指定模型，且系统未能自动应用默认模型。")

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

    # --- 模板方法 ---

    async def run(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        模板方法：执行由工作者生成的指令流，并内置上下文准备、取消和错误处理逻辑。
        Manager 不再直接执行指令，而是产出指令流供 Executor 执行。
        """
        try:
            db_chat, history_messages = await self._prepare_context(chat_id, assistant_message_id)

            llm_input = await self._prepare_llm_input(db_chat, history_messages)

            worker_output_generator = worker.generate(llm_input)

            async for output in worker_output_generator:
                if await stream_manager.is_cancellation_requested(assistant_message_id):
                    raise asyncio.CancelledError("Generation was cancelled by user request.")

                instruction_generator = self._translate_worker_output_to_instructions(output)

                async for instruction in instruction_generator:
                    yield instruction

        except (asyncio.CancelledError, Exception) as e:
            overall_status = schemas_enums.MessageStatus.FAILED

            if isinstance(e, asyncio.CancelledError):
                print(f"[AbstractGenerateManager] Task cancelled for message '{assistant_message_id}'.")
                overall_status = schemas_enums.MessageStatus.COMPLETED
            else:
                print(
                    f"[AbstractGenerateManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
                traceback.print_exc()
                overall_status = schemas_enums.MessageStatus.FAILED

            # 发生异常时，调用子类的清理逻辑生成指令
            async for instruction in self._cleanup_on_exception(assistant_message_id, overall_status, e):
                yield instruction
