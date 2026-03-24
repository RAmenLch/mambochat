# backend/services/generation/worker/openai_worker.py

from backend.services.generation.worker.decode import BaseDecode, OpenAiDecode
from backend.services.generation.worker.extended_chat_openai_model import ExtendedChatOpenAI
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from services.generation.agent.log_callback import RawPayloadLoggingCallback


class OpenAiWorker(ChatWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ExtendedChatOpenAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """

    def get_decode(self) -> BaseDecode:
        return OpenAiDecode()

    def _create_model(self, llm_input: LLMInput) -> ExtendedChatOpenAI:
        """
        根据 LLMInput 配置创建 ExtendedChatOpenAI 实例。
        """
        # 适配新架构：从 llm_config提取基础参数
        model_kwargs = llm_input.llm_config.parameters.copy()
        stream = model_kwargs.pop("stream", True) # 既然是 Worker，默认应该支持流式

        # 适配新架构：从 llm_config处理代理
        openai_proxy = llm_input.llm_config.proxy_url if llm_input.llm_config.proxy_url else None

        return ExtendedChatOpenAI(
            model=llm_input.llm_config.model_id,
            api_key=llm_input.llm_config.api_key,
            base_url=llm_input.llm_config.api_host.rstrip("/"),
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.llm_config.timeout,
            streaming=stream,
            default_headers={
                "HTTP-Referer": "https://github.com/RAmenLch/mambochat",  # Optional. Site URL for rankings on openrouter.ai.
                "X-Title": "MamboChat",  # Optional. Site title for rankings on openrouter.ai.
            },
            callbacks=[RawPayloadLoggingCallback("abc")]
        )

