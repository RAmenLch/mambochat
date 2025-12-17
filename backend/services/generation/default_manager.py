# backend/services/generation/default_manager.py
import json
import base64
from typing import AsyncGenerator, List, Dict, Any, Optional
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.services.generation.react_manager import ReActAgentChatGenerateManager
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    SaveAndPersistFile
)
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.crud import setting_crud, file_crud
from backend.schemas import enums as schemas_enums
from backend.models import chat_model
from backend.models.base_model import generate_uuid
from backend.services.storage_service import storage_service
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS

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
        if key in ["max_context_messages", "stream", "enabled_mcp_ids"]:
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


async def _build_zip_history_messages_payload(history_messages: List[chat_model.Message]) -> List[chat_model.Message]:
    """
    构建包含压缩历史的消息列表。
    如果发现启用了 ZipHistory 的子消息，则将其视为对话的新起点（摘要），
    并丢弃其之前的消息。
    """
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
    return effective_history


async def _build_llm_messages_payload(
        db_session: AsyncSession,
        history_messages: List[chat_model.Message],
        is_multimodal_enabled: bool
) -> List[Dict[str, Any]]:
    """
    【共享函数】根据历史消息列表，构建用于LLM输入的标准化消息负载。
    此函数包含上下文过滤、多模态内容组装以及 MCP 工具调用的重组逻辑。
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
    current_tool_calls = []
    pending_tool_results = []

    total_messages = len(history_messages)
    for msg_index, msg in enumerate(history_messages):
        # 计算消息的新旧程度排名 (1=最新, 2=次新, ...)
        message_recency_rank = total_messages - msg_index

        # 如果角色切换，先保存之前的累积内容
        if current_role != msg.role and current_role is not None:
            # 1. 构建并添加主消息
            message_obj = {"role": current_role}

            merged_parts = merge_text_parts(current_content_parts)
            if merged_parts:
                content = merged_parts[0]['text'] if len(merged_parts) == 1 and merged_parts[0][
                    'type'] == 'text' else merged_parts
            else:
                # 某些模型（如OpenAI）允许只发tool_calls不发content，但通常需要content不为None
                if not current_tool_calls:
                    # 如果既没内容也没工具调用，跳过空消息
                    pass
                else:
                    message_obj["content"] = None

            if "content" in message_obj or current_tool_calls:
                # 再次确认content存在，上面逻辑可能导致KeyError如果content未设置
                if "content" in message_obj:
                    pass
                else:
                    # 补全 content 为 None
                    message_obj["content"] = None

            if current_tool_calls:
                message_obj["tool_calls"] = current_tool_calls

            if message_obj.get("content") is not None or "tool_calls" in message_obj:
                messages_payload.append(message_obj)

            # 2. 紧随其后添加工具结果消息 (Role: Tool)
            if pending_tool_results:
                messages_payload.extend(pending_tool_results)

            # 重置状态
            current_content_parts = []
            current_tool_calls = []
            pending_tool_results = []

        current_role = msg.role

        for sub in msg.sub_messages:
            # --- MCP 工具调用处理 ---
            if sub.type == schemas_enums.SubMessageType.MCP_TOOL.value:
                try:
                    tool_data = json.loads(sub.content)
                    # 构建 Assistant 消息中的 tool_calls 部分
                    current_tool_calls.append({
                        "id": tool_data.get("tool_call_id"),
                        "type": "function",
                        "function": {
                            "name": tool_data.get("name"),
                            "arguments": tool_data.get("arguments")
                        }
                    })
                    # 构建后续的 Tool 消息
                    # 注意：只有当 result 不为 None 时才添加结果消息（表示已执行）
                    if tool_data.get("result") is not None:
                        pending_tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_data.get("tool_call_id"),
                            "content": tool_data.get("result")
                        })
                except json.JSONDecodeError:
                    continue
                continue  # 处理完 MCP_TOOL 后继续下一个 sub_message

            # --- 常规内容处理 ---
            cpl = None
            try:
                config_str = sub.config if isinstance(sub.config, str) else json.dumps(sub.config or {})
                if config_str:
                    config_dict = json.loads(config_str)
                    cpl = config_dict.get('context_participation_length')
            except (json.JSONDecodeError, TypeError):
                pass

            if cpl == 0:
                continue

            if isinstance(cpl, int) and cpl > 0:
                if message_recency_rank > cpl:
                    continue

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

    # 处理循环结束后的最后一条消息
    if current_role:
        message_obj = {"role": current_role}
        merged_parts = merge_text_parts(current_content_parts)
        if merged_parts:
            content = merged_parts[0]['text'] if len(merged_parts) == 1 and merged_parts[0][
                'type'] == 'text' else merged_parts
            message_obj["content"] = content
        else:
            if not current_tool_calls:
                pass
            else:
                message_obj["content"] = None

        if current_tool_calls:
            message_obj["tool_calls"] = current_tool_calls

        if message_obj.get("content") is not None or "tool_calls" in message_obj:
            messages_payload.append(message_obj)

        if pending_tool_results:
            messages_payload.extend(pending_tool_results)

    return messages_payload


class DefaultGenerateManager(ReActAgentChatGenerateManager):
    """
    默认生成管理器，负责根据聊天记录准备LLM输入（包括处理图片、文本文件和已启用的压缩历史）。
    继承自 ReActAgentChatGenerateManager，因此原生支持工具调用和 ReAct 循环。
    扩展了对 generated image 输出的处理。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)

    async def _prepare_llm_input(
            self,
            db_chat: chat_model.Chat,
            history_messages: List[chat_model.Message]
    ) -> LLMInput:
        """
        根据会话配置和历史消息，准备发送给 Worker 的标准化 LLMInput。
        """
        if not db_chat.ai_model or not db_chat.ai_model.provider:
            raise ValueError("会话未配置有效的AI模型或服务商。")

        provider = db_chat.ai_model.provider
        model = db_chat.ai_model

        # 1. 查找并应用已启用的压缩历史
        effective_history = await _build_zip_history_messages_payload(history_messages)

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

    async def _handle_custom_worker_output(self, output: WorkerOutput) -> AsyncGenerator[BaseInstruction, None]:
        """
        处理基类不支持的自定义输出类型，例如生成的图片。
        不再执行IO操作，而是发出 SaveAndPersistFile 指令交由 Executor 处理。
        """
        if output.type == "image_content":
            try:
                # 解析 Base64 数据字符串
                # 格式通常为: data:image/png;base64,iVBORw0KGgo...
                header, encoded_data = output.content.split(',', 1)
                mime_type = header.split(';')[0].split(':')[1]
                file_extension = mime_type.split('/')[-1] if '/' in mime_type else 'bin'

                filename = f"generated_image.{file_extension}"

                # 1. 预生成 ID
                file_id = generate_uuid()
                sub_message_id = generate_uuid()

                # 2. 发出保存并持久化文件的指令 (包含完整数据负载)
                # Executor 将负责解码、物理存储 IO 和数据库记录创建
                yield SaveAndPersistFile(
                    file_id=file_id,
                    filename=filename,
                    base64_data=encoded_data,
                    mime_type=mime_type,
                    management_type=schemas_enums.FileManagementType.SUB_MESSAGE.value
                )

                # 3. 发出创建子消息的指令 (引用文件ID)
                # 只有上一条指令成功执行，这一条才会被处理
                yield CreateSubMessage(
                    sub_message_id=sub_message_id,
                    type=schemas_enums.SubMessageType.FILE.value,
                    sortOrder=2,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    initial_content=file_id,
                    config={}
                )

            except Exception as e:
                print(f"Error processing generated image instruction: {e}")
                # 如果主内容正在生成，尝试将错误追加进去
                if self._content_id:
                    yield AppendToSubMessage(
                        sub_message_id=self._content_id,
                        content=f"\n\n**处理生成图片指令时出错: {e}**"
                    )
                else:
                    raise e
