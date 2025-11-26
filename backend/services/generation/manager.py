# backend/services/generation/manager.py
import asyncio
import json
import base64
from typing import AsyncGenerator, List, Dict, Any, Optional
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AbstractGenerateManager
from .instructions import (
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus,
    BaseInstruction
)
from .llm_io import LLMInput, WorkerOutput
from ...crud import message_crud, setting_crud, file_crud
from ...schemas import enums as schemas_enums
from ...models import chat_model
from ...services.storage_service import storage_service
from ...config.llm_parameters import SUPPORTED_LLM_PARAMETERS

# --- Parameter Building Utilities ---

# Create a lookup map for efficient access to parameter definitions
_param_definition_map = {param.key: param for param in SUPPORTED_LLM_PARAMETERS}


def _build_llm_parameters(flat_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a flat parameter dictionary from a Chat object into a structured
    dictionary suitable for an LLM API call, based on path definitions.
    """
    structured_params = {}

    def set_nested_value(d: dict, path: list[str], value: Any):
        """Recursively sets a value in a nested dictionary based on a path list."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    if not flat_params:
        return {}

    for key, value in flat_params.items():
        # Skip special parameters that are not sent directly to the LLM's parameter body
        if key in ["max_context_messages", "stream"]:
            continue

        definition = _param_definition_map.get(key)
        if definition:
            set_nested_value(structured_params, definition.path, value)

    return structured_params


# --- Text MIME Types for Context ---
SUPPORTED_TEXT_MIME_TYPES = {
    "text/plain", "text/markdown", "text/csv", "text/html", "text/css",
    "application/json", "text/xml", "text/x-python", "application/javascript",
    "text/typescript", "text/x-java-source", "text/x-csharp", "text/x-c",
    "text/x-c++src", "text/x-go", "text/x-ruby", "application/sql", "application/x-sh"
}


async def _build_llm_messages_payload(
        db_session: AsyncSession,
        history_messages: List[chat_model.Message],
        is_multimodal_enabled: bool
) -> List[Dict[str, Any]]:
    """
    【共享函数】根据历史消息列表，构建用于LLM输入的标准化消息负载。
    此函数包含上下文过滤和多模态内容组装的核心逻辑。
    """
    messages_payload = []

    def merge_text_parts(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not parts:
            return []
        merged = []
        buffer = ""
        for part in parts:
            if part['type'] == 'text':
                buffer += part['text'] + "\n"
            else:
                if buffer:
                    merged.append({'type': 'text', 'text': buffer.strip()})
                    buffer = ""
                merged.append(part)
        if buffer:
            merged.append({'type': 'text', 'text': buffer.strip()})
        return merged

    current_role = None
    current_content_parts = []

    total_messages = len(history_messages)
    for msg_index, msg in enumerate(history_messages):
        # 计算消息的新旧程度排名 (1=最新, 2=次新, ...)
        message_recency_rank = total_messages - msg_index

        if current_role != msg.role and current_role is not None:
            merged_parts = merge_text_parts(current_content_parts)
            if merged_parts:
                content = merged_parts[0]['text'] if len(merged_parts) == 1 and merged_parts[0][
                    'type'] == 'text' else merged_parts
                messages_payload.append({"role": current_role, "content": content})
            current_content_parts = []

        current_role = msg.role

        for sub in msg.sub_messages:
            cpl = None
            try:
                config_str = sub.config if isinstance(sub.config, str) else json.dumps(sub.config or {})
                if config_str:
                    config_dict = json.loads(config_str)
                    cpl = config_dict.get('context_participation_length')
            except (json.JSONDecodeError, TypeError):
                # 解析失败则 cpl 保持为 None, 按默认逻辑(参与上下文)处理
                pass

            # 如果 cpl 为 0, 则此 sub-message 不参与上下文
            if cpl == 0:
                continue

            # 如果 cpl 是正整数, 检查当前 message 是否在指定的“新”范围内
            if isinstance(cpl, int) and cpl > 0:
                if message_recency_rank > cpl:
                    continue

            # 其他情况 (cpl 为 None 或满足条件) 则正常加入上下文
            if sub.type == schemas_enums.SubMessageType.FILE.value:
                db_file = await file_crud.get_file(db_session, sub.content)
                if not db_file:
                    continue

                try:
                    if db_file.mime_type.startswith("image/"):
                        if not is_multimodal_enabled:
                            continue
                        image_bytes = await storage_service.read_bytes(db_file.storage_path)
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        data_url = f"data:{db_file.mime_type};base64,{base64_image}"
                        current_content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                    elif db_file.mime_type in SUPPORTED_TEXT_MIME_TYPES:
                        text_bytes = await storage_service.read_bytes(db_file.storage_path)
                        file_content = text_bytes.decode('utf-8')
                        current_content_parts.append({
                            "type": "text",
                            "text": f"\n--- Start of file: {db_file.filename} ---\n{file_content}\n--- End of file: {db_file.filename} ---"
                        })
                except Exception as e:
                    print(f"Error processing file {db_file.id} for context: {e}")
            elif sub.type != schemas_enums.SubMessageType.ZIP_HISTORY.value:
                current_content_parts.append({"type": "text", "text": sub.content})

    if current_role and current_content_parts:
        merged_parts = merge_text_parts(current_content_parts)
        if merged_parts:
            content = merged_parts[0]['text'] if len(merged_parts) == 1 and merged_parts[0][
                'type'] == 'text' else merged_parts
            messages_payload.append({"role": current_role, "content": content})

    return messages_payload


class DefaultGenerateManager(AbstractGenerateManager):
    """
    默认生成管理器，负责根据聊天记录准备LLM输入（包括处理图片、文本文件和已启用的压缩历史），
    并能将LLM的输出（包括生成的图片）翻译成数据库和流指令。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self._main_content_started = False
        self._reasoning_content_started = False
        self._final_usage_data: Optional[Dict] = None

    async def _prepare_llm_input(
            self,
            db_chat: chat_model.Chat,
            history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        根据会话配置和历史消息，准备发送给 Worker 的标准化 LLMInput。
        此函数包含上下文过滤、压缩历史替换和多模态内容组装的核心逻辑。
        """
        if not db_chat.ai_model or not db_chat.ai_model.provider:
            raise ValueError("会话未配置有效的AI模型或服务商。")

        provider = db_chat.ai_model.provider
        model = db_chat.ai_model

        # 1. 查找并应用已启用的压缩历史
        effective_history = history_messages
        last_enabled_zip_index = -1
        zip_content = None

        for i in range(len(history_messages) - 1, -1, -1):
            msg = history_messages[i]
            for sub in msg.sub_messages:
                if sub.type == schemas_enums.SubMessageType.ZIP_HISTORY.value:
                    try:
                        config = json.loads(sub.config) if isinstance(sub.config, str) else sub.config
                        if config and config.get('zip_enable') is True:
                            last_enabled_zip_index = i
                            zip_content = sub.content
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
            if last_enabled_zip_index != -1:
                break

        if last_enabled_zip_index != -1 and zip_content:
            # 构造虚拟消息来代表压缩历史
            user_sub = SimpleNamespace(content="对之前的对话进行了总结摘要。",
                                       type=schemas_enums.SubMessageType.NORMAL.value, config='{}')
            user_msg = SimpleNamespace(role=schemas_enums.MessageRole.USER.value, sub_messages=[user_sub])

            assistant_sub = SimpleNamespace(content=zip_content, type=schemas_enums.SubMessageType.NORMAL.value,
                                            config='{}')
            assistant_msg = SimpleNamespace(role=schemas_enums.MessageRole.ASSISTANT.value,
                                            sub_messages=[assistant_sub])

            # 构建新的有效历史记录
            effective_history = [user_msg, assistant_msg] + history_messages[last_enabled_zip_index + 1:]

        # 2. 准备多模态和消息负载
        meta_config = {}
        if model.meta_config and isinstance(model.meta_config, str):
            try:
                meta_config = json.loads(model.meta_config)
            except json.JSONDecodeError:
                meta_config = {}

        is_multimodal_enabled = 'image' in (meta_config.get('input_modalities') or [])

        messages_payload = await _build_llm_messages_payload(
            self.db_session, effective_history, is_multimodal_enabled
        )

        if db_chat.systemPrompt:
            messages_payload.insert(0, {"role": "system", "content": db_chat.systemPrompt})

        # 3. 准备模型参数和连接配置
        raw_model_params = {}
        if db_chat.modelParameters:
            try:
                params_str = db_chat.modelParameters
                raw_model_params = json.loads(params_str) if isinstance(params_str, str) else params_str
            except (json.JSONDecodeError, TypeError):
                pass

        # Build structured parameters for the API call using the central definition
        api_params = _build_llm_parameters(raw_model_params)

        # Manually add the 'stream' parameter as it's a special case for controlling worker behavior
        if 'stream' in raw_model_params:
            api_params['stream'] = raw_model_params.get('stream')

        proxy_url = None
        if provider.use_proxy:
            proxy_enabled_setting = await setting_crud.get_setting(self.db_session, "proxy_enabled")
            if proxy_enabled_setting and proxy_enabled_setting.value == 'True':
                proxy_url_setting = await setting_crud.get_setting(self.db_session, "proxy_url")
                if proxy_url_setting and proxy_url_setting.value:
                    proxy_url = proxy_url_setting.value

        return LLMInput(
            model_id=model.modelId,
            messages=messages_payload,
            parameters=api_params,
            api_host=provider.apiHost,
            api_key=provider.apiKey,
            proxy_url=proxy_url
        )

    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将标准化的 WorkerOutput 翻译成具体的数据库和UI指令流。
        """
        if output.type == "reasoning":
            if not self._reasoning_content_started:
                yield CreateSubMessage(
                    temp_ref_id="reasoning_content", type=schemas_enums.SubMessageType.REASONING.value, sortOrder=0,
                    status=schemas_enums.MessageStatus.GENERATING,
                    config={"context_participation_length": 0}
                )
                self._reasoning_content_started = True
            yield AppendToSubMessage(temp_ref_id="reasoning_content", content=output.content)

        elif output.type == "content":
            if not self._main_content_started:
                yield CreateSubMessage(
                    temp_ref_id="main_content", type=schemas_enums.SubMessageType.NORMAL.value, sortOrder=1,
                    status=schemas_enums.MessageStatus.GENERATING
                )
                self._main_content_started = True
            yield AppendToSubMessage(temp_ref_id="main_content", content=output.content)

        elif output.type == "image_content":
            try:
                header, encoded_data = output.content.split(',', 1)
                mime_type = header.split(';')[0].split(':')[1]
                file_extension = mime_type.split('/')[-1] if '/' in mime_type else 'bin'

                image_bytes = base64.b64decode(encoded_data)

                filename = f"generated_image.{file_extension}"
                storage_path = await storage_service.save_from_bytes(
                    data=image_bytes,
                    filename=filename,
                    sub_path="chat_attachments"
                )

                db_file = await file_crud.create_file(
                    db=self.db_session,
                    filename=filename,
                    storage_path=storage_path,
                    mime_type=mime_type,
                    size=len(image_bytes),
                    management_type=schemas_enums.FileManagementType.SUB_MESSAGE.value
                )

                yield CreateSubMessage(
                    temp_ref_id=f"generated_image_{db_file.id}",
                    type=schemas_enums.SubMessageType.FILE.value,
                    sortOrder=2,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    initial_content=db_file.id,
                    config={}
                )
            except Exception as e:
                print(f"Error processing generated image: {e}")
                if self._main_content_started:
                    yield AppendToSubMessage(temp_ref_id="main_content", content=f"\n\n**处理生成图片时出错: {e}**")

        elif output.type == "usage":
            if output.usage:
                self._final_usage_data = output.usage

        elif output.type == "done":
            if self._main_content_started:
                yield UpdateSubMessageStatus(temp_ref_id="main_content", status=schemas_enums.MessageStatus.COMPLETED)
            if self._reasoning_content_started:
                yield UpdateSubMessageStatus(temp_ref_id="reasoning_content",
                                             status=schemas_enums.MessageStatus.COMPLETED)

            if self._final_usage_data:
                usage_content = json.dumps(self._final_usage_data)
                yield CreateSubMessage(
                    temp_ref_id="usage_info",
                    type=schemas_enums.SubMessageType.USAGE.value,
                    sortOrder=99,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    initial_content=usage_content,
                    config={"context_participation_length": 0}
                )

            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            # Worker 捕获的错误会通过这个分支，并最终在 _cleanup_on_exception 中被处理
            raise RuntimeError(output.content)

    async def _cleanup_on_exception(self, assistant_message_id: str, final_status: schemas_enums.MessageStatus,
                                    exception: Optional[Exception] = None):
        """
        在任务异常或被取消时，更新所有子消息状态，并创建一条包含错误信息的子消息。
        """
        error_content = None
        if exception:
            if isinstance(exception, RuntimeError):
                error_content = str(exception)
            elif isinstance(exception, asyncio.CancelledError):
                error_content = "生成被用户取消。"
            else:
                error_content = f"发生未处理的异常: {str(exception)}"

        # 1. 确保所有正在生成的分区状态被更新
        for temp_ref_id, sub_id in self.temp_ref_id_map.items():
            try:
                db_sub_message = await message_crud.get_sub_message(self.db_session, sub_id)
                if db_sub_message and db_sub_message.status == schemas_enums.MessageStatus.GENERATING.value:
                    await self._process_instruction(
                        UpdateSubMessageStatus(temp_ref_id=temp_ref_id, status=final_status),
                        assistant_message_id
                    )
            except Exception as e_inner:
                print(f"[DefaultGenerateManager] Error updating sub-message {sub_id} during cleanup: {e_inner}")

        # 2. 将错误信息展示给用户
        if error_content:
            main_content_id = self.temp_ref_id_map.get("main_content")
            if main_content_id:
                # 如果主内容分区已存在，将错误追加到末尾
                await self._process_instruction(
                    AppendToSubMessage(temp_ref_id="main_content", content=f"\n\n**错误:** {error_content}"),
                    assistant_message_id
                )
            else:
                # 如果没有任何分区，创建一个新的分区来显示错误
                await self._process_instruction(
                    CreateSubMessage(
                        temp_ref_id="error_content",
                        type=schemas_enums.SubMessageType.NORMAL.value,
                        sortOrder=1,
                        status=final_status,
                        initial_content=error_content
                    ),
                    assistant_message_id
                )
