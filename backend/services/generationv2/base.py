from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any

from backend.services.generation.llm_io import LLMInput


class AbstractGenerateWorker(ABC):
    """
    第二代抽象生成工作者 (V2)。

    职责变更：
    V2 Worker 不再是单纯的 API 客户端，而是充当 Agent 的角色。
    它负责封装 LangChain/LangGraph 的运行时逻辑，包括模型调用、工具执行决策等。

    输出变更：
    不再输出自定义的 WorkerOutput，而是直接流式输出 LangChain 的原始事件或消息块
    (如 ChatGenerationChunk, AIMessageChunk 或 LangGraph 的状态更新事件)，
    交由 Manager 层进行翻译和指令转换。
    """

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
