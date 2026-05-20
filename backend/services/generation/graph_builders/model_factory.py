# backend/services/generation/graph_builders/model_factory.py

from langchain_core.language_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.schemas.enums import ProviderWorkerType
from backend.services.generation.core.llm_io import ModelConfig, RunTimeConfig
from backend.services.generation.agent.log_callback import RawPayloadLoggingCallback
from backend.services.generation.worker.extended_chat_openai_model import ExtendedChatOpenAI
from backend.services.generation.worker.deepseek_chat_model import ChatDeepSeek


class ModelFactory:
    """
    模型工厂。
    负责根据 ModelConfig 动态实例化对应的 LangChain ChatModel。
    """
    DEFAULT_MAX_RETRIES = 3

    @staticmethod
    def create_model(model_config: ModelConfig, run_time_config: RunTimeConfig) -> BaseChatModel:
        params_copy = model_config.parameters.copy()
        worker_type = params_copy.pop("_worker_type", ProviderWorkerType.OPENAI.value)
        stream = params_copy.pop("stream", True)
        max_retries = model_config.max_retries or self.DEFAULT_MAX_RETRIES

        callbacks = [RawPayloadLoggingCallback(run_time_config)]

        if worker_type == ProviderWorkerType.ANTHROPIC.value:
            thinking = params_copy.pop("thinking", {"type": "enabled", "budget_tokens": 32000})
            return ChatAnthropic(
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
            include_thoughts = params_copy.pop("include_thoughts", True)
            return ChatGoogleGenerativeAI(
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
            thinking = params_copy.pop("thinking", None)
            reasoning_effort = params_copy.pop("reasoning_effort", None)
            return ChatDeepSeek(
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
            return ExtendedChatOpenAI(
                model=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/"),
                model_kwargs=params_copy,
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
