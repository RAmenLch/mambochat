# backend/services/generation/openai_worker.py
import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Tuple, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from ...models import chat_model
from ...schemas import enums as schemas_enums
from ...crud import setting_crud
from .base import AbstractGenerateWorker
from .instructions import BaseInstruction, CreateSubMessage, AppendToSubMessage, UpdateSubMessageStatus, SetFinalStatus


async def _get_http_client_with_proxy(
        db: AsyncSession,
        use_proxy_flag: bool,
        timeout: int = 300
) -> httpx.AsyncClient:
    """
    根据需要创建一个配置了代理的 httpx.AsyncClient 实例。
    """
    proxy_url = None
    if use_proxy_flag:
        proxy_enabled_setting = await setting_crud.get_setting(db, "proxy_enabled")
        if proxy_enabled_setting and proxy_enabled_setting.value == 'True':
            proxy_url_setting = await setting_crud.get_setting(db, "proxy_url")
            if proxy_url_setting and proxy_url_setting.value:
                proxy_url = proxy_url_setting.value

    return httpx.AsyncClient(proxy=proxy_url, timeout=timeout)


def _prepare_llm_request_data(
        db_chat: chat_model.Chat,
        history_messages: List[chat_model.Message]
) -> Tuple[Dict[str, Any], Dict[str, Any], str, bool]:
    """
    根据会话配置和历史消息，准备发送给 LLM API 的 headers, payload, host 和 use_proxy 标志。
    此函数包含根据 submessage 配置过滤上下文的核心逻辑。
    """
    if not db_chat.ai_model or not db_chat.ai_model.provider:
        raise ValueError("会话未配置有效的AI模型或服务商。")

    provider = db_chat.ai_model.provider
    model = db_chat.ai_model

    headers = {
        "Authorization": f"Bearer {provider.apiKey}",
        "Content-Type": "application/json",
    }

    # 1. 将所有历史子消息扁平化处理
    flat_submessages = []
    for msg in history_messages:
        # 假设 sub_messages 在从数据库获取时已按 sortOrder 排序
        for sub in msg.sub_messages:
            flat_submessages.append((msg.role, sub))

    # 2. 根据 config 过滤子消息
    total_sub_count = len(flat_submessages)
    filtered_submessages = []
    for i, (role, sub) in enumerate(flat_submessages):
        pos_from_end = total_sub_count - i

        # 安全地解析 config
        N = None
        if sub.config and isinstance(sub.config, str):
            try:
                config_dict = json.loads(sub.config)
                N = config_dict.get('context_participation_length')
            except (json.JSONDecodeError, TypeError):
                pass
        elif sub.config and isinstance(sub.config, dict):
            N = sub.config.get('context_participation_length')

        # 应用过滤规则
        if N is None:  # 未设置，保留
            filtered_submessages.append((role, sub))
            continue
        if N == 0:  # 设置为0，删除
            continue
        if N > 0 and pos_from_end <= N:  # 设置为N，且在倒数N位或更后面，保留
            filtered_submessages.append((role, sub))
            continue
        # 其他情况（例如 pos_from_end > N），删除

    # 3. 将过滤后的子消息重新聚合为 LLM API 的格式
    messages_payload = []
    if db_chat.systemPrompt:
        messages_payload.append({"role": "system", "content": db_chat.systemPrompt})

    if filtered_submessages:
        # 按角色对相邻的子消息进行分组
        current_role = filtered_submessages[0][0]
        current_content_parts = [filtered_submessages[0][1].content]

        for i in range(1, len(filtered_submessages)):
            role, sub = filtered_submessages[i]
            if role == current_role:
                current_content_parts.append(sub.content)
            else:
                messages_payload.append({"role": current_role, "content": "\n".join(current_content_parts)})
                current_role = role
                current_content_parts = [sub.content]

        # 追加最后一个聚合的消息
        if current_content_parts:
            messages_payload.append({"role": current_role, "content": "\n".join(current_content_parts)})

    # 4. 准备最终的 payload
    model_params = {}
    if db_chat.modelParameters:
        try:
            params_str = db_chat.modelParameters
            model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
        except (json.JSONDecodeError, TypeError):
            pass

    model_params.pop('max_context_messages', None)
    model_params.pop('stream', None)

    payload = {
        "model": model.modelId,
        "messages": messages_payload,
        **model_params
    }

    return headers, payload, provider.apiHost, provider.use_proxy


class OpenAIGenerateWorker(AbstractGenerateWorker):
    """
    OpenAI 生成工作者，负责与 OpenAI 兼容的 API 交互并生成指令。
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def generate(
            self,
            db_chat: chat_model.Chat,
            history_messages: List[chat_model.Message],
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        与 OpenAI API 通信，解析流式响应，并生成指令。
        """
        headers, payload, api_host, use_proxy = _prepare_llm_request_data(db_chat, history_messages)
        payload["stream"] = True

        main_content_sub_message_started = False
        reasoning_content_sub_message_started = False

        try:
            async with await _get_http_client_with_proxy(self.db_session, use_proxy_flag=use_proxy) as client:
                async with client.stream("POST", f"{api_host.rstrip('/')}/chat/completions", headers=headers,
                                         json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices")
                                if choices and len(choices) > 0:
                                    delta = choices[0].get("delta", {})

                                    reason_chunk = delta.get("reasoning_content")
                                    if reason_chunk:
                                        if not reasoning_content_sub_message_started:
                                            yield CreateSubMessage(
                                                temp_ref_id="reasoning_content",
                                                type="Reasoning",
                                                sortOrder=0,
                                                status=schemas_enums.MessageStatus.GENERATING,
                                                initial_content=reason_chunk,
                                                config={"context_participation_length": 0}
                                            )
                                            reasoning_content_sub_message_started = True
                                        else:
                                            yield AppendToSubMessage(
                                                temp_ref_id="reasoning_content",
                                                content=reason_chunk
                                            )

                                    content_chunk = delta.get("content")
                                    if content_chunk:
                                        if not main_content_sub_message_started:
                                            yield CreateSubMessage(
                                                temp_ref_id="main_content",
                                                type="Normal",
                                                sortOrder=1,
                                                status=schemas_enums.MessageStatus.GENERATING,
                                                initial_content=content_chunk
                                            )
                                            main_content_sub_message_started = True
                                        else:
                                            yield AppendToSubMessage(
                                                temp_ref_id="main_content",
                                                content=content_chunk
                                            )


                            except json.JSONDecodeError:
                                continue

            if main_content_sub_message_started:
                yield UpdateSubMessageStatus(temp_ref_id="main_content", status=schemas_enums.MessageStatus.COMPLETED)
            if reasoning_content_sub_message_started:
                yield UpdateSubMessageStatus(temp_ref_id="reasoning_content",
                                             status=schemas_enums.MessageStatus.COMPLETED)
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        except Exception as e:
            error_message = f"\n\n**错误: {e}**"
            # 确保至少有一个子消息可以承载错误信息
            if not main_content_sub_message_started and not reasoning_content_sub_message_started:
                yield CreateSubMessage(
                    temp_ref_id="main_content",
                    type="Normal",
                    sortOrder=1,
                    status=schemas_enums.MessageStatus.FAILED,
                    initial_content=f"生成失败: {e}"
                )
            else:
                if main_content_sub_message_started:
                    yield AppendToSubMessage(temp_ref_id="main_content", content=error_message)
                    yield UpdateSubMessageStatus(temp_ref_id="main_content", status=schemas_enums.MessageStatus.FAILED)
                if reasoning_content_sub_message_started:
                    # 如果思维链也失败，可以单独处理或仅标记状态
                    yield UpdateSubMessageStatus(temp_ref_id="reasoning_content",
                                                 status=schemas_enums.MessageStatus.FAILED)

            yield SetFinalStatus(status=schemas_enums.MessageStatus.FAILED)
