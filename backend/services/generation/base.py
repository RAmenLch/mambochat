# backend/services/generation/base.py
from abc import ABC, abstractmethod
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple

from ...models import chat_model
from .instructions import BaseInstruction
from ...schemas import enums as schemas_enums
from ...services.stream_manager_service import stream_manager
from ...crud import message_crud


class AbstractGenerateWorker(ABC):
    """
    抽象生成工作者。负责与LLM API交互，并将LLM的原始输出转换为一系列标准化指令。
    它不应直接与数据库或流管理器交互。
    """
    @abstractmethod
    async def generate(
        self,
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message],
        assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        与LLM API通信并生成指令流。

        Args:
            db_chat: 当前聊天会话的数据库对象，包含模型和提供商信息。
            history_messages: 用于LLM上下文的历史消息列表。
            assistant_message_id: 当前正在生成的助手消息的ID。

        Yields:
            BaseInstruction: 一系列指令，供Manager执行。
        """
        pass


class AbstractGenerateManager(ABC):
    """
    抽象生成管理器。它定义了执行指令流的模板方法，包括上下文准备、循环、取消检查和异常处理。
    子类需要实现具体的上下文准备、指令处理和清理逻辑。
    """

    def __init__(self, db_session: Any):
        self.db_session = db_session
        self.temp_ref_id_map: Dict[str, str] = {}

    @abstractmethod
    async def _prepare_context(
        self,
        chat_id: str,
        assistant_message_id: str
    ) -> Tuple[chat_model.Chat, List[chat_model.Message]]:
        """
        子类必须实现此方法以准备生成所需的上下文。

        Args:
            chat_id: 当前会话的ID。
            assistant_message_id: 当前助手消息的ID。

        Returns:
            一个包含 db_chat 对象和 history_messages 列表的元组。
        """
        pass

    @abstractmethod
    async def _process_instruction(
        self,
        instruction: BaseInstruction,
        assistant_message_id: str
    ) -> Optional[schemas_enums.MessageStatus]:
        """
        子类必须实现此方法以处理单个指令。
        如果指令是 SetFinalStatus，则应返回其状态值。

        Args:
            instruction: 从工作者接收到的指令。
            assistant_message_id: 当前助手消息的ID。

        Returns:
            如果指令是 SetFinalStatus，则返回其状态；否则返回 None。
        """
        pass

    @abstractmethod
    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus):
        """
        子类必须实现此方法，在发生异常（包括取消）时，
        负责将所有正在生成的子消息更新为最终状态。

        Args:
            assistant_message_id: 当前助手消息的ID。
            final_status: 整个任务应该被设置的最终状态（如 COMPLETED 或 FAILED）。
        """
        pass

    async def run(
        self,
        worker: AbstractGenerateWorker,
        chat_id: str,
        assistant_message_id: str
    ) -> schemas_enums.MessageStatus:
        """
        模板方法：执行由工作者生成的指令流，并内置上下文准备、取消和错误处理逻辑。

        Args:
            worker: 负责生成指令的工作者实例。
            chat_id: 当前会话的ID。
            assistant_message_id: 当前正在生成的助手消息的ID。

        Returns:
            schemas_enums.MessageStatus: 整个生成任务的最终状态。
        """
        overall_status = schemas_enums.MessageStatus.FAILED
        try:
            db_chat, history_messages = await self._prepare_context(chat_id, assistant_message_id)

            generator = worker.generate(
                db_chat=db_chat,
                history_messages=history_messages,
                assistant_message_id=assistant_message_id
            )
            async for instruction in generator:
                if await stream_manager.is_cancellation_requested(assistant_message_id):
                    print(f"[AbstractGenerateManager] Cancellation detected for '{assistant_message_id}'.")
                    raise asyncio.CancelledError

                status_from_instruction = await self._process_instruction(instruction, assistant_message_id)
                if status_from_instruction:
                    overall_status = status_from_instruction

        except asyncio.CancelledError:
            print(f"[AbstractGenerateManager] Task cancelled for message '{assistant_message_id}'.")
            overall_status = schemas_enums.MessageStatus.COMPLETED
            await self._cleanup_on_exception(assistant_message_id, overall_status)

        except Exception as e:
            print(f"[AbstractGenerateManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
            overall_status = schemas_enums.MessageStatus.FAILED
            await self._cleanup_on_exception(assistant_message_id, overall_status)

        return overall_status
