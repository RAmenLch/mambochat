# backend/services/generation/managers/base_manager.py

import asyncio
import traceback
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.core.instructions import BaseInstruction
from backend.schemas import enums as schemas_enums


class AbstractGenerateManager(ABC):
    """
    V2 生成管理器抽象基类。
    定义了标准的 run 方法模板，处理通用的异常捕获和生命周期管理。
    具体的业务逻辑（如 ReAct 循环、标题生成、摘要生成）由子类实现。
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def run(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        模板方法：执行生成任务。
        包裹了异常处理和取消逻辑，将具体的执行委托给 _execute_generation。

        Args:
            worker: V2 版本的生成工作者 (Agent)
            chat_id: 会话 ID
            assistant_message_id: 目标消息 ID (或任务 ID)

        Yields:
            BaseInstruction: 指令流
        """
        try:
            async for instruction in self._execute_generation(worker, chat_id, assistant_message_id):
                yield instruction

        except (asyncio.CancelledError, Exception) as e:
            overall_status = schemas_enums.MessageStatus.FAILED

            if isinstance(e, asyncio.CancelledError):
                print(f"[AbstractGenerateManager] Task cancelled for message '{assistant_message_id}'.")
                overall_status = schemas_enums.MessageStatus.COMPLETED
            else:
                print(f"[AbstractGenerateManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
                traceback.print_exc()
                overall_status = schemas_enums.MessageStatus.FAILED

            # 调用子类的清理逻辑
            async for instruction in self._cleanup_on_exception(assistant_message_id, overall_status, e, chat_id):
                yield instruction

    @abstractmethod
    async def _execute_generation(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        核心生成逻辑，由子类实现。
        负责初始化 LLMInputBuilderV2，调用 worker.generate，并解析输出流。
        """
        pass

    @abstractmethod
    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None,
            chat_id: Optional[str] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        异常清理钩子，由子类实现。
        负责关闭未完成的子消息、生成错误提示等。
        """
        pass
