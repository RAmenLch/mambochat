# backend/services/generation/graph_builders/model_factory.py

from langchain_core.language_models import BaseChatModel

from backend.schemas.enums import ProviderWorkerType
from backend.services.generation.core.llm_io import ModelConfig, RunTimeConfig
from backend.services.generation.agent.log_callback import RawPayloadLoggingCallback


class ModelFactory:
    """
    模型工厂。
    负责根据 ModelConfig 动态实例化对应的 LangChain ChatModel。
    """
    DEFAULT_MAX_RETRIES = 3

    @staticmethod
    def create_model(model_config: ModelConfig, run_time_config: RunTimeConfig) -> BaseChatModel:
        if model_config is None:
            raise ValueError(
                "ModelConfig is None — 该 Agent 没有绑定模型配置。"
                "请检查 Agent 是否设置了 aiModelId 或继承了父 Agent 的 llm_config。"
            )
        params_copy = model_config.parameters.copy()
        worker_type = params_copy.pop("_worker_type", ProviderWorkerType.OPENAI.value)
        stream = params_copy.pop("stream", True)
        max_retries = model_config.max_retries or ModelFactory.DEFAULT_MAX_RETRIES

        callbacks = [RawPayloadLoggingCallback(run_time_config)]

        if worker_type == ProviderWorkerType.ANTHROPIC.value:
            from langchain_anthropic import ChatAnthropic
            thinking = params_copy.pop("thinking", {"type": "enabled", "budget_tokens": 32000})
            model = ChatAnthropic(
                model_name=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/").rstrip("/v1"),
                thinking=thinking,
                model_kwargs=params_copy,
                anthropic_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                stop=None,
                callbacks=callbacks,
                max_retries=max_retries
            )

        elif worker_type == ProviderWorkerType.GOOGLE.value:
            from langchain_google_genai import ChatGoogleGenerativeAI
            include_thoughts = params_copy.pop("include_thoughts", True)
            model = ChatGoogleGenerativeAI(
                model=model_config.model_id,
                api_key=model_config.api_key,
                include_thoughts=include_thoughts,
                base_url=model_config.api_host.rstrip("/").rstrip("/v1beta"),
                model_kwargs=params_copy,
                openai_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                callbacks=callbacks,
                max_retries=max_retries
            )

        elif worker_type == ProviderWorkerType.DEEPSEEK.value:
            from backend.services.generation.worker.deepseek_chat_model import ChatDeepSeek
            thinking = params_copy.pop("thinking", None)
            reasoning_effort = params_copy.pop("reasoning_effort", None)
            model = ChatDeepSeek(
                model=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/"),
                model_kwargs=params_copy,
                openai_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                callbacks=callbacks,
                max_retries=max_retries,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                stream_chunk_timeout=(
                    model_config.stream_chunk_timeout
                    if model_config.stream_chunk_timeout is not None
                    else model_config.timeout * 2
                )
            )

        else:
            from backend.services.generation.worker.extended_chat_openai_model import ExtendedChatOpenAI
            extra_body = params_copy.pop("extra_body", None)
            model = ExtendedChatOpenAI(
                model=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/"),
                model_kwargs=params_copy,
                extra_body=extra_body,
                openai_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                default_headers={
                    "HTTP-Referer": "https://github.com/RAmenLch/mambochat",
                    "X-Title": "MamboChat",
                },
                callbacks=callbacks,
                max_retries=max_retries,
                stream_chunk_timeout=(
                    model_config.stream_chunk_timeout
                    if model_config.stream_chunk_timeout is not None
                    else model_config.timeout * 2
                )
            )

        # 注入 model profile，供 summarization fraction 模式使用
        ModelFactory._inject_profile(model, model_config)

        return model

    @staticmethod
    def _inject_profile(model: BaseChatModel, model_config: ModelConfig) -> None:
        """如果 auto-resolve 未产生 profile 且有 context_length，则手动注入。"""
        if model.profile is not None:
            return
        cl = model_config.context_length
        if cl is not None and cl > 0:
            model.profile = {"max_input_tokens": cl}
