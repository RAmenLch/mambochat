from langchain_google_genai import ChatGoogleGenerativeAI
from backend.services.generation.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from backend.services.generation.worker.decode import OpenAiDecode, BaseDecode, GoogleDecode


class GoogleWorker(ChatWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ExtendedChatOpenAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """
    @staticmethod
    def get_decode() -> type[BaseDecode]:
        return GoogleDecode


    def _create_model(self, llm_input: LLMInput) -> ChatGoogleGenerativeAI:
        """
        根据 LLMInput 配置创建 ExtendedChatOpenAI 实例。
        """
        # 提取基础参数
        model_kwargs = llm_input.parameters.copy()
        stream = model_kwargs.pop("stream", True) # 既然是 Worker，默认应该支持流式
        include_thoughts = model_kwargs.pop("include_thoughts", True)
        # 处理代理
        openai_proxy = llm_input.proxy_url if llm_input.proxy_url else None
        url = llm_input.api_host.rstrip("/").rstrip("/v1beta")
        return ChatGoogleGenerativeAI(
            model=llm_input.model_id,
            api_key=llm_input.api_key,
            include_thoughts=include_thoughts,
            base_url=url,
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.timeout,
            streaming=stream
        )
