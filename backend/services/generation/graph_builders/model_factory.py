# backend/services/generation/graph_builders/model_factory.py

import inspect
from functools import lru_cache
from typing import Optional, Tuple

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

    #: worker_type -> LangChain 模型类的 ls_provider（须与下方 create_model 的类选择保持一致）。
    _LS_PROVIDER_BY_WORKER = {
        ProviderWorkerType.ANTHROPIC.value: "anthropic",
        ProviderWorkerType.GOOGLE.value: "google_genai",
        ProviderWorkerType.DEEPSEEK.value: "openai",   # ChatDeepSeek 继承 ChatOpenAI
        ProviderWorkerType.OPENAI.value: "openai",
    }

    @staticmethod
    def ls_provider_for_worker(worker_type: Optional[str]) -> str:
        """返回该 worker_type 对应 LangChain 模型类的 ``ls_provider``。

        用于把重建消息的 ``response_metadata["model_provider"]`` 对齐到摘要中间件
        实际使用的模型（其 ``_get_ls_params()["ls_provider"]``），从而命中
        ``LCSummarizationMiddleware`` 的 reported-token 兜底判定。
        未知类型回退为 OpenAI 兼容（``ExtendedChatOpenAI``）。
        """
        return ModelFactory._LS_PROVIDER_BY_WORKER.get(worker_type, "openai")

    #: worker_type -> 该适配器是否会把 reasoning 重新回传给 provider。
    #: ChatDeepSeek 会在请求体里显式加回 reasoning_content；ChatOpenAI（含
    #: ExtendedChatOpenAI）的 _convert_message_to_dict 不会转发 reasoning_content。
    _RESENDS_REASONING_BY_WORKER = {
        ProviderWorkerType.DEEPSEEK.value: True,
    }

    @staticmethod
    def resends_reasoning(worker_type: Optional[str]) -> bool:
        """该 worker_type 的模型是否会把 reasoning 重新发给 provider。

        用于决定摘要触发的本地 token 预估是否需计入 reasoning（mambo_agents 的
        ``SummarizationConfig.include_reasoning``）：只有会回传 reasoning 的模型
        才应计入，否则会高估 token 导致过早压缩。
        """
        return ModelFactory._RESENDS_REASONING_BY_WORKER.get(worker_type, False)

    @staticmethod
    @lru_cache(maxsize=1)
    def _chat_completions_params() -> frozenset:
        """OpenAI SDK ``chat.completions.create`` 接受的顶层参数名。

        ``ChatOpenAI`` 把 ``model_kwargs`` 原样并入请求体后调用
        ``chat.completions.create(**payload)``，SDK 对签名外的键直接抛
        ``TypeError: got an unexpected keyword argument``，故以该签名作为
        “可留在 model_kwargs 里”的白名单。
        """
        from openai.resources.chat.completions import AsyncCompletions

        return frozenset(inspect.signature(AsyncCompletions.create).parameters) - {"self"}

    @classmethod
    def _split_model_params(cls, params: dict) -> Tuple[dict, Optional[dict]]:
        """把生成参数拆成 (model_kwargs, extra_body)。

        provider 扩展参数（``reasoning`` / ``include_reasoning`` / ``top_k`` /
        ``do_sample`` 等）不在 SDK 签名内，必须由 ``extra_body`` 携带——SDK 会在发送前
        把它平铺进 JSON body，provider 拿到的字段与写在顶层完全一致；否则请求会以
        ``TypeError: ... got an unexpected keyword argument`` 失败。

        顺带避免 ``reasoning`` 之类的键出现在 payload 顶层：那会让
        ``ChatOpenAI._use_responses_api`` 把请求静默切到 Responses API。
        """
        known = cls._chat_completions_params()
        model_kwargs: dict = {}
        extra_body: dict = {}
        for key, value in params.items():
            if key == "extra_body":
                if isinstance(value, dict):
                    extra_body.update(value)
            elif key in known:
                model_kwargs[key] = value
            else:
                extra_body[key] = value
        return model_kwargs, (extra_body or None)

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
            model_kwargs, extra_body = ModelFactory._split_model_params(params_copy)
            model = ChatDeepSeek(
                model=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/"),
                model_kwargs=model_kwargs,
                extra_body=extra_body,
                openai_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                stream_usage=True,
                # ChatDeepSeek._get_request_payload 只构造 chat/completions 请求体
                use_responses_api=False,
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
            model_kwargs, extra_body = ModelFactory._split_model_params(params_copy)
            model = ExtendedChatOpenAI(
                model=model_config.model_id,
                api_key=model_config.api_key,
                base_url=model_config.api_host.rstrip("/"),
                model_kwargs=model_kwargs,
                extra_body=extra_body,
                openai_proxy=model_config.proxy_url,
                timeout=model_config.timeout,
                streaming=stream,
                stream_usage=True,
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
