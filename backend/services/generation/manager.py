# backend/services/generation/manager.py
import asyncio
import json
import base64
import traceback
from typing import AsyncGenerator, List, Dict, Any, Optional
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.services.generation.base import AbstractGenerateManager
from backend.services.generation.instructions import (
    CreateSubMessage,
    AppendToSubMessage,
    UpdateSubMessageStatus,
    SetFinalStatus,
    BaseInstruction
)
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.crud import message_crud, setting_crud, file_crud
from backend.schemas import enums as schemas_enums
from backend.models import chat_model
from backend.services.storage_service import storage_service
from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS
from backend.config.mcp_config import MCP_SERVER_ENABLED, BING_MCP_SERVER_PATH
from backend.services.mcp_service import McpClientService

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

async def _build_zip_history_messages_payload(history_messages:List[chat_model.Message]) -> List[chat_model.Message]:
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
                message_obj["content"] = content
            else:
                # 某些模型（如OpenAI）允许只发tool_calls不发content，但通常需要content不为None
                if not current_tool_calls:
                    # 如果既没内容也没工具调用，跳过空消息
                    pass
                else:
                    message_obj["content"] = None

            if current_tool_calls:
                message_obj["tool_calls"] = current_tool_calls

            if "content" in message_obj or "tool_calls" in message_obj:
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
                continue # 处理完 MCP_TOOL 后继续下一个 sub_message

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

        if "content" in message_obj or "tool_calls" in message_obj:
            messages_payload.append(message_obj)

        if pending_tool_results:
            messages_payload.extend(pending_tool_results)

    return messages_payload


class DefaultGenerateManager(AbstractGenerateManager):
    """
    默认生成管理器，负责根据聊天记录准备LLM输入（包括处理图片、文本文件和已启用的压缩历史），
    并能将LLM的输出（包括生成的图片）翻译成数据库和流指令。
    支持 ReAct (Reasoning + Acting) 模式，可调用 MCP 工具。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self._main_content_started = False
        self._reasoning_content_started = False
        self._final_usage_data: Optional[Dict] = None
        self._current_turn_tool_calls: List[Dict] = [] # 暂存当前轮次生成的工具调用

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

        elif output.type == "tool_call":
            # 处理工具调用指令
            if output.tool_calls:
                self._current_turn_tool_calls = [] # 清空旧数据
                for tool_call in output.tool_calls:
                    # 构造工具调用的存储结构
                    tool_data = {
                        "tool_call_id": tool_call.get("id"),
                        "name": tool_call.get("function", {}).get("name"),
                        "arguments": tool_call.get("function", {}).get("arguments"),
                        "result": None,
                        "is_error": False
                    }
                    json_content = json.dumps(tool_data, ensure_ascii=False)

                    # 记录到内存以便后续执行
                    self._current_turn_tool_calls.append({
                        "data": tool_data,
                        "temp_ref_id": f"tool_{tool_call.get('id')}"
                    })

                    # 发出创建子消息指令
                    yield CreateSubMessage(
                        temp_ref_id=f"tool_{tool_call.get('id')}",
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        sortOrder=2, # 放在内容之后
                        status=schemas_enums.MessageStatus.GENERATING,
                        initial_content=json_content,
                        config={"is_minimal": True}
                    )

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

            # 如果本轮没有工具调用，则生成 Usage 和 FinalStatus
            # 如果有工具调用，Manager 的 run 循环会继续，暂不结束
            if not self._current_turn_tool_calls:
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

    async def run(
            self,
            worker: Any,
            chat_id: str,
            assistant_message_id: str
    ) -> schemas_enums.MessageStatus:
        """
        执行 ReAct (Reasoning + Acting) 循环。
        """
        overall_status = schemas_enums.MessageStatus.FAILED
        mcp_service = None

        try:
            # 1. 准备初始上下文
            db_chat, history_messages = await self._prepare_context(chat_id, assistant_message_id)

            # 2. 初始化 MCP 服务
            enabled_mcp_ids = []
            if db_chat.modelParameters:
                try:
                    params = json.loads(db_chat.modelParameters) if isinstance(db_chat.modelParameters, str) else db_chat.modelParameters
                    enabled_mcp_ids = params.get("enabled_mcp_ids", [])
                except:
                    pass

            openai_tools = None
            if MCP_SERVER_ENABLED and enabled_mcp_ids:
                # 目前仅支持单一 Bing MCP Server，未来可根据 IDs 动态加载
                mcp_service = McpClientService(str(BING_MCP_SERVER_PATH))
                await mcp_service.connect()
                openai_tools = await mcp_service.get_openai_tools()

            # 3. ReAct 循环
            current_history = history_messages
            # 用于在循环中累积当前 Assistant 消息的生成内容，以便在下一轮作为上下文
            current_assistant_content_buffer = []
            current_assistant_tool_calls_buffer = []

            while True:
                # 准备 LLM 输入
                llm_input = await self._prepare_llm_input(db_chat, current_history)

                # 注入工具
                if openai_tools:
                    llm_input.tools = openai_tools
                    # llm_input.tool_choice = "auto"

                # 生成
                worker_output_generator = worker.generate(llm_input)

                # 重置本轮工具调用缓存
                self._current_turn_tool_calls = []

                async for output in worker_output_generator:
                    if await asyncio.to_thread(lambda: False): # Placeholder for cancellation check if needed
                        pass

                    instruction_generator = self._translate_worker_output_to_instructions(output)

                    async for instruction in instruction_generator:
                        status_from_instruction = await self._process_instruction(instruction, assistant_message_id)
                        if status_from_instruction:
                            overall_status = status_from_instruction

                    # 累积内容用于上下文回填
                    if output.type == "content" and output.content:
                        current_assistant_content_buffer.append(output.content)

                # 检查是否有工具调用需要执行
                if not self._current_turn_tool_calls:
                    break # 没有工具调用，生成结束

                # --- 执行阶段 (Acting) ---

                # 1. 执行工具并更新 SubMessage
                for tool_item in self._current_turn_tool_calls:
                    tool_data = tool_item["data"]
                    temp_ref_id = tool_item["temp_ref_id"]

                    try:
                        args = json.loads(tool_data["arguments"])
                        result_str = await mcp_service.call_tool(tool_data["name"], args)
                        tool_data["result"] = result_str
                    except Exception as e:
                        tool_data["result"] = f"Error executing tool: {str(e)}"
                        tool_data["is_error"] = True

                    # 更新 SubMessage
                    updated_content = json.dumps(tool_data, ensure_ascii=False)

                    # 这里我们直接复用 _process_instruction 来更新内容和状态
                    # 注意：CreateSubMessage 的 initial_content 已经写入了 DB
                    # 我们需要一种方式更新 SubMessage 的 content。
                    # 现有的 AppendToSubMessage 是追加，不适合替换 JSON。
                    # 但我们知道 SubMessage ID，可以直接调用 CRUD。

                    sub_message_id = self.temp_ref_id_map.get(temp_ref_id)
                    if sub_message_id:
                        # 更新内容
                        await message_crud.update_sub_message(
                            self.db_session,
                            sub_message_id,
                            schemas.SubMessageUpdate(content=updated_content)
                        )
                        # 更新状态
                        await self._process_instruction(
                            UpdateSubMessageStatus(temp_ref_id=temp_ref_id, status=schemas_enums.MessageStatus.COMPLETED),
                            assistant_message_id
                        )

                        # 推送更新事件 (Hack: 模拟 append 事件来触发前端刷新，或者前端监听 status_update 后重新拉取)
                        # 更佳做法是 stream_manager 支持 update 类型，但这里简化处理
                        # 实际上 _process_instruction 中的 UpdateSubMessageStatus 已经推送了 status_update
                        # 我们再推送一个自定义事件或者利用前端对 status_update 的响应

                    # 记录到 buffer 以备下一轮上下文构建
                    current_assistant_tool_calls_buffer.append({
                        "id": tool_data["tool_call_id"],
                        "type": "function",
                        "function": {
                            "name": tool_data["name"],
                            "arguments": tool_data["arguments"]
                        }
                    })

                # 2. 更新上下文 (current_history) 以便下一轮生成
                # 我们需要构造虚拟的 Message 对象添加到 current_history

                # A. 构造当前的 Assistant 消息 (包含文本和工具调用)
                assistant_content = "".join(current_assistant_content_buffer) if current_assistant_content_buffer else None

                # 构造一个由 SubMessage 组成的虚拟 Message
                virtual_subs = []
                if assistant_content:
                    virtual_subs.append(SimpleNamespace(
                        type=schemas_enums.SubMessageType.NORMAL.value,
                        content=assistant_content,
                        config={}
                    ))

                for tc in self._current_turn_tool_calls:
                    # 这里存入的是执行后的完整 JSON
                    virtual_subs.append(SimpleNamespace(
                        type=schemas_enums.SubMessageType.MCP_TOOL.value,
                        content=json.dumps(tc["data"], ensure_ascii=False),
                        config={}
                    ))

                virtual_assistant_msg = SimpleNamespace(
                    role=schemas_enums.MessageRole.ASSISTANT.value,
                    sub_messages=virtual_subs
                )

                # B. 将虚拟 Assistant 消息加入历史
                # 注意：如果是第一轮之后的轮次，我们需要替换掉上一次循环添加的 Assistant 消息吗？
                # ReAct 模式下，通常是：
                # User -> Assistant (Call Tool) -> Tool (Result) -> Assistant (Answer)
                # 我们的 current_history 初始包含 User。
                # 第一轮后：User, Assistant(Call)
                # 第二轮前：我们需要 User, Assistant(Call), Tool(Result)
                # 所以我们只需要追加即可。

                # 但是，current_assistant_content_buffer 在多轮中可能会累积？
                # 不，每一轮 worker 输出的是 *增量* 或者是 *新的* 思考。
                # 如果模型在第二轮继续输出文本，那是新的文本。
                # 所以我们需要把本轮产生的 Assistant 消息固定下来加入历史。

                current_history.append(virtual_assistant_msg)

                # 重置 buffer，因为下一轮是新的 Assistant 消息
                current_assistant_content_buffer = []
                current_assistant_tool_calls_buffer = []

                # C. 构造 Tool 消息 (Results) 并不需要显式作为 Message 对象加入，
                # 因为 _build_llm_messages_payload 会根据 Assistant 消息中的 MCP_TOOL SubMessage
                # 自动生成后续的 Tool Role 消息。
                # 只要我们在 virtual_assistant_msg 中包含了带 result 的 MCP_TOOL SubMessage 即可。

                # 继续下一轮循环
                continue

        except (asyncio.CancelledError, Exception) as e:
            if isinstance(e, asyncio.CancelledError):
                print(f"[DefaultGenerateManager] Task cancelled for message '{assistant_message_id}'.")
                overall_status = schemas_enums.MessageStatus.COMPLETED
            else:
                print(f"[DefaultGenerateManager] Unhandled error in run loop for message '{assistant_message_id}': {e}")
                traceback.print_exc()
                overall_status = schemas_enums.MessageStatus.FAILED

            await self._cleanup_on_exception(assistant_message_id, overall_status, e)

        finally:
            if mcp_service:
                await mcp_service.close()

        return overall_status

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
