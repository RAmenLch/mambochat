from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any, Dict, Tuple, Union

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import BaseDecode

StreamEvent = Union[ToolMessage, AIMessageChunk, AIMessage, Dict[str, Any]]


class AbstractGenerateWorker(ABC):
    @abstractmethod
    def resolve_decoder(self, message: StreamEvent) -> BaseDecode:
        pass

    @abstractmethod
    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[Tuple[str, StreamEvent], None]:
        if False:
            yield
