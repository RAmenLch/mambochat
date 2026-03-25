from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any

from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import DefaultLangChainDecode,BaseDecode


from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.decode import BaseDecode

class AbstractGenerateWorker(ABC):
    @abstractmethod
    def resolve_decoder(self, message: Any) -> BaseDecode:
        pass

    @abstractmethod
    async def generate(self, llm_input: LLMInput) -> AsyncGenerator[Any, None]:
        if False:
            yield