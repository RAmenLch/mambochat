# backend/services/generation/worker/simple_worker.py

from typing import AsyncGenerator, Tuple

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker, StreamEvent
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.graph_builders.model_factory import ModelFactory


class SimpleWorker(AbstractGenerateWorker):
    """
    简化的 Worker：直接通过 ModelFactory 创建 LLM 实例并流式调用，
    不依赖 LangGraph agent、checkpoint 恢复、虚拟文件系统等重级设施。

    适用于标题生成、历史压缩等纯 LLM 调用场景。
    """

    async def generate(
            self,
            llm_input: LLMInput
    ) -> AsyncGenerator[Tuple[str, StreamEvent], None]:

        model = ModelFactory.create_model(
            llm_input.agent_config.llm_config,
            llm_input.run_time_config
        )

        if llm_input.agent_config.tools:
            model = model.bind_tools(llm_input.agent_config.tools)

        messages = self._convert_messages(llm_input.context.messages)

        async for chunk in model.astream(messages):
            yield "messages", chunk
