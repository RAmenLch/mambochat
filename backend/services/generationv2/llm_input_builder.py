from typing import List, Optional
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend.services.generationv2.llm_io import LLMInput


class LLMInputBuilderV2(LLMInputBuilder):
    """
    LLM 输入构建器 V2。
    继承自 V1 构建器，复用其素材加载、切片、过滤和 Payload 构建逻辑。
    主要差异在于：
    1. 生成 V2 版本的 LLMInput 对象。
    2. 支持注入 LangChain 的 BaseTool 对象列表，而非原始字典。
    """

    def __init__(self, db: AsyncSession, chat_id: str):
        super().__init__(db, chat_id)
        self._tools: Optional[List[BaseTool]] = None

    def set_tools(self, tools: List[BaseTool]) -> "LLMInputBuilderV2":
        """
        设置 LangChain 工具列表。
        这些工具将直接传递给 V2 Worker (Agent)。
        """
        self._tools = tools
        return self

    async def build(self) -> LLMInput:
        """
        执行构建流程，返回 V2 版本的 LLMInput。
        """
        # 1. 加载素材 (复用 V1 逻辑)
        await self._load_materials()

        # 2. 确定模型和 System Prompt (复用 V1 逻辑)
        model = await self._resolve_model()
        provider = model.provider

        system_prompt = self._system_prompt_override
        if system_prompt is None:
            system_prompt = self.chat.systemPrompt

        # 3. 应用压缩历史逻辑 (复用 V1 逻辑)
        effective_history = self.history
        if self._enable_zip_history:
            effective_history = await self._apply_zip_history_logic(effective_history)

        # 4. 应用切片逻辑 (复用 V1 逻辑)
        effective_history = self._apply_slicing(effective_history)

        # 5. 核心转换：将消息对象集合转化为 Payload 结构 (复用 V1 逻辑)
        # 注意：这里生成的 payload 仍是 List[Dict]，OpenAiWorker 会将其转换为 LangChain Message 对象
        messages_payload = await self._build_payload(effective_history)

        # 6. 注入 System Prompt
        if system_prompt:
            messages_payload.insert(0, {"role": "system", "content": system_prompt})

        # 7. 组装参数 (复用 V1 逻辑)
        api_params = {}
        if not self._global_model_keys:
            api_params = self._map_parameters(self.chat.modelParameters)

        proxy_url = None
        if provider.use_proxy and self.settings.get("proxy_enabled") == "True":
            proxy_url = self.settings.get("proxy_url")

        # 8. 返回 V2 LLMInput
        return LLMInput(
            model_id=model.modelId,
            messages=messages_payload,
            parameters=api_params,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url,
            tools=self._tools,  # 注入 BaseTool 对象列表
            tool_choice=None    # Agent 模式下通常由模型自动决定
        )
