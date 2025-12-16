# backend/services/generation/abstract_worker.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from backend.services.generation.llm_io import LLMInput, WorkerOutput


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

