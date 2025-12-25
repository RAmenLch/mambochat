import asyncio
import traceback
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.abstract_worker import AbstractGenerateWorker
from backend.services.generation.instructions import BaseInstruction



class AbstractGenerateManager(ABC):
    """
    一个“框架式”的生成管理器。它处理所有通用流程，
    子类只需实现特定的业务逻辑。
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
        模板方法：执行由工作者生成的指令流，并内置上下文准备、取消和错误处理逻辑。
        Manager 不再直接执行指令，而是产出指令流供 Executor 执行。
        """
