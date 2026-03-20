# backend/services/generation/executor/dispatcher.py

from typing import Dict, Type, Callable, Awaitable, Optional, TypeVar, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.services.generation.core.instructions import (
    BaseInstruction, CreateSubMessage, AppendToSubMessage, UpdateSubMessageContent,
    UpdateSubMessageStatus, UpdateSubMessageConfig, SetFinalStatus,
    UpdateChatName, SaveAndPersistFile, UpdateZipHistorySubMessage, NotifyUser
)
from backend.services.generation.executor import handlers

# ==========================================
# 阶段三：强化指令分发器的泛型类型安全
# 定义泛型类型变量，绑定到 BaseInstruction
# ==========================================
T_Instruction = TypeVar('T_Instruction', bound=BaseInstruction)


class InstructionDispatcher:
    """
    指令分发器 (替代原 InstructionExecutor)。
    采用策略模式，将纯数据指令路由到对应的处理函数。
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        # 内部字典存储异构的 Handlers，为了兼容各种具体的 Instruction 子类，入参类型放宽为 Any
        self._handlers: Dict[
            Type[BaseInstruction],
            Callable[[Any, str, str, AsyncSession], Awaitable[Optional[schemas.enums.MessageStatus]]]
        ] = {}
        self._register_default_handlers()

    def register(
        self,
        instruction_type: Type[T_Instruction],
        handler: Callable[[T_Instruction, str, str, AsyncSession], Awaitable[Optional[schemas.enums.MessageStatus]]]
    ) -> None:
        """
        注册自定义的指令处理器。
        使用泛型约束，确保传入的 handler 接收的指令类型与 instruction_type 严格一致，
        从而在编写代码时获得 IDE 的严格类型检查和代码提示。
        """
        self._handlers[instruction_type] = handler  # type: ignore

    def _register_default_handlers(self) -> None:
        """注册所有内置的指令处理器"""
        self.register(CreateSubMessage, handlers.handle_create_sub_message)
        self.register(AppendToSubMessage, handlers.handle_append_to_sub_message)
        self.register(UpdateSubMessageContent, handlers.handle_update_sub_message_content)
        self.register(UpdateSubMessageStatus, handlers.handle_update_sub_message_status)
        self.register(UpdateSubMessageConfig, handlers.handle_update_sub_message_config)
        self.register(SaveAndPersistFile, handlers.handle_save_and_persist_file)
        self.register(UpdateChatName, handlers.handle_update_chat_name)
        self.register(UpdateZipHistorySubMessage, handlers.handle_update_zip_history)
        self.register(NotifyUser, handlers.handle_notify_user)
        self.register(SetFinalStatus, handlers.handle_set_final_status)

    async def execute(
            self,
            instruction: BaseInstruction,
            chat_id: str,
            assistant_message_id: str
    ) -> Optional[schemas.enums.MessageStatus]:
        """
        执行单个指令。

        Args:
            instruction: 具体的指令对象。
            chat_id: 会话ID。
            assistant_message_id: 关联的Assistant消息ID。

        Returns:
            如果是 SetFinalStatus 指令，返回最终状态；否则返回 None。
        """
        instruction_type = type(instruction)
        handler = self._handlers.get(instruction_type)

        if not handler:
            print(f"[InstructionDispatcher] Warning: Unhandled instruction type {instruction_type}")
            return None

        # 动态调用对应的 handler
        return await handler(instruction, chat_id, assistant_message_id, self.db_session)
