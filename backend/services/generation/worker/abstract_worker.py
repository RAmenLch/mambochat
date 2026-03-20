from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any

from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import DefaultLangChainDecode,BaseDecode


class AbstractGenerateWorker(ABC):

    def get_decode(self) -> BaseDecode:
        return DefaultLangChainDecode()

    @abstractmethod
    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[Any, None]:
        """
        启动 Agent 并流式返回执行过程中的事件。

        Args:
            llm_input: 包含模型配置、历史消息、工具定义等上下文的输入对象。

        Yields:
            Any: LangChain/LangGraph 的流式事件 (chunks, updates, etc.)。
                 具体类型取决于 Worker 内部使用的 stream_mode。
        """
        if False:
            yield