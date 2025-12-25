# backend/services/generation/simple_manager.py
import asyncio
import json
import traceback
from abc import abstractmethod
from typing import AsyncGenerator, Optional, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.generation.abstract_manager import AbstractGenerateManager
from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus
)
from backend.services.generation.llm_io import WorkerOutput, LLMInput
from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid
from backend.services.stream_manager_service import stream_manager


class SimpleChatGenerateManager(AbstractGenerateManager):
    """
    简单聊天生成管理器。
    适用于单轮、非代理、一次性生成的任务。
    处理基本的 reasoning 和 content 流，以及 usage 统计。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self._reasoning_id: Optional[str] = None
        self._content_id: Optional[str] = None
        self._usage_id: Optional[str] = None
        self._final_usage_data: Optional[Dict] = None

    @abstractmethod
    async def _prepare_llm_input(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> LLMInput:
        """
        【业务逻辑插槽 1】
        将数据库对象转换为标准化的 LLM 输入。
        这是实现者定义“如何提问”的地方 (例如，构建 prompt)。
        """
        pass


    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将 Worker 输出转换为指令。
        维护内部 ID 状态。
        """
        if output.type == "reasoning":
            if not self._reasoning_id:
                self._reasoning_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._reasoning_id,
                    type=schemas_enums.SubMessageType.REASONING.value,
                    sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
            yield AppendToSubMessage(sub_message_id=self._reasoning_id, content=output.content)

        elif output.type == "content":
            if not self._content_id:
                self._content_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=self._content_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
            yield AppendToSubMessage(sub_message_id=self._content_id, content=output.content)

        elif output.type == "usage":
            if output.usage:
                self._final_usage_data = output.usage

        elif output.type == "done":
            # 完成所有活跃分区
            if self._content_id:
                yield UpdateSubMessageStatus(
                    sub_message_id=self._content_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )
            if self._reasoning_id:
                yield UpdateSubMessageStatus(
                    sub_message_id=self._reasoning_id,
                    status=schemas_enums.MessageStatus.COMPLETED
                )

            # 生成 Usage 分区
            if self._final_usage_data:
                self._usage_id = generate_uuid()
                usage_content = json.dumps(self._final_usage_data)
                yield CreateSubMessage(
                    sub_message_id=self._usage_id,
                    type=schemas_enums.SubMessageType.USAGE.value,
                    sortOrder=99,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    initial_content=usage_content,
                    config={"context_participation_length": 0}
                )

            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            # 错误通常会抛出异常，由 _cleanup_on_exception 处理
            # 但如果 Worker 输出 error 类型块，也可以直接抛出
            raise RuntimeError(output.content)

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        清理逻辑：更新正在生成的分区状态，并创建错误消息分区。
        """
        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            # asyncio.CancelledError 通常不需要错误内容，只需结束状态
            elif not isinstance(exception, (type(None),)): # Check if it is a real exception
                 # CancelledError is handled in run loop wrapper mostly, but if passed here:
                 if "CancelledError" in str(type(exception)):
                     error_content = "生成被用户取消。"
                 else:
                     error_content = f"发生未处理的异常: {str(exception)}"

        # 1. 更新活跃分区状态
        if self._reasoning_id:
             yield UpdateSubMessageStatus(sub_message_id=self._reasoning_id, status=final_status)
        if self._content_id:
             yield UpdateSubMessageStatus(sub_message_id=self._content_id, status=final_status)

        # 2. 展示错误信息
        if error_content:
            if self._content_id:
                yield AppendToSubMessage(
                    sub_message_id=self._content_id,
                    content=f"\n\n**错误:** {error_content}"
                )
            else:
                error_id = generate_uuid()
                yield CreateSubMessage(
                    sub_message_id=error_id,
                    type=schemas_enums.SubMessageType.NORMAL.value,
                    sortOrder=1,
                    status=final_status,
                    initial_content=error_content
                )

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
            # 不再由基类直接读取数据库 (_prepare_context 已移除)，
            # 而是将 ID 传递给子类，由子类利用 LLMInputBuilder 进行数据的读取和构建。
            llm_input = await self._prepare_llm_input(chat_id,assistant_message_id)

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