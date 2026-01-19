from backend.services.generation.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from backend.services.generation.worker.deepseek_chat_model import ChatDeepSeek


class DeepSeekWorker(ChatWorker):
    """
    DeepSeek 生成工作者。
    继承自 ChatWorker，针对 DeepSeek 的思考模式（Reasoning Mode）进行了适配。
    """

    def _create_model(self, llm_input: LLMInput) -> ChatDeepSeek:
        """
        根据 LLMInput 配置创建自定义的 ChatDeepSeek 实例。
        使用自定义的 ChatDeepSeek 类以修复工具调用时的 payload 构建问题。
        """
        model_kwargs = llm_input.parameters.copy()
        stream = model_kwargs.pop("stream", True)

        openai_proxy = llm_input.proxy_url if llm_input.proxy_url else None

        return ChatDeepSeek(
            model=llm_input.model_id,
            api_key=llm_input.api_key,
            base_url=llm_input.api_host.rstrip("/"),
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.timeout,
            streaming=stream
        )
