from langchain_google_genai import ChatGoogleGenerativeAI
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.worker.chat_worker import ChatWorker
from backend.services.generation.worker.decode import BaseDecode, GoogleDecode
from backend.services.generation.agent.log_callback import RawPayloadLoggingCallback


class GoogleWorker(ChatWorker):
    """
    基于 LangChain/LangGraph 的生成工作者。

    它接收包含配置和工具的 LLMInput，构建 ChatGoogleGenerativeAI 模型，
    并使用 create_react_agent 启动一个 ReAct 代理循环。
    输出流为 LangChain 的原生消息块 (BaseMessageChunk) 或状态更新，
    由 Manager 负责翻译。
    """

    def get_decode(self) -> BaseDecode:
        return GoogleDecode()

    def _create_model(self, llm_input: LLMInput) -> ChatGoogleGenerativeAI:
        """
        根据 LLMInput 配置创建 ChatGoogleGenerativeAI 实例。
        """
        # 提取基础参数 (适配新架构：从 llm_config 读取)
        model_kwargs = llm_input.llm_config.parameters.copy()
        stream = model_kwargs.pop("stream", True)  # 既然是 Worker，默认应该支持流式
        include_thoughts = model_kwargs.pop("include_thoughts", True)

        # 处理代理 (适配新架构：从 llm_config 读取)
        openai_proxy = llm_input.llm_config.proxy_url if llm_input.llm_config.proxy_url else None
        url = llm_input.llm_config.api_host.rstrip("/").rstrip("/v1beta")

        return ChatGoogleGenerativeAI(
            model=llm_input.llm_config.model_id,
            api_key=llm_input.llm_config.api_key,
            include_thoughts=include_thoughts,
            base_url=url,
            model_kwargs=model_kwargs,
            openai_proxy=openai_proxy,
            timeout=llm_input.llm_config.timeout,
            streaming=stream,
            callbacks=[RawPayloadLoggingCallback(llm_input.run_time_config)]
        )

