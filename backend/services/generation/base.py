# backend/services/generation/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List
from ...models import chat_model
from .instructions import BaseInstruction

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
    抽象生成管理器。负责接收并执行来自工作者的指令流，与数据库和流管理器交互。
    它不应直接与LLM API交互。
    """
    @abstractmethod
    async def run(
        self,
        worker: AbstractGenerateWorker,
        assistant_message_id: str
    ):
        """
        执行由工作者生成的指令流。

        Args:
            worker: 负责生成指令的工作者实例。
            assistant_message_id: 当前正在生成的助手消息的ID。
        """
        pass

