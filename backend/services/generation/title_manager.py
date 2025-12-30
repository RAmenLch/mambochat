# backend/services/generation/title_manager.py
import json
from typing import AsyncGenerator, Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import SubMessageType
from backend.services.generation.simple_manager import SimpleChatGenerateManager
from backend.services.generation.instructions import (
    BaseInstruction,
    SetFinalStatus,
    UpdateChatName,
    NotifyUser
)
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend import schemas


class TitleGenerationContext(BaseModel):
    """标题生成任务的上下文信息"""
    chat_id: str


class TitleGenerateManager(SimpleChatGenerateManager):
    """
    负责为会话自动生成标题的管理器。
    它准备一个特殊的LLM输入，请求模型生成标题，然后解析响应并更新会话名称。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.chat_id: Optional[str] = None
        self.error_occurred = False

    async def _prepare_llm_input(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> LLMInput:
        """
        准备用于生成标题的LLM输入。
        使用 LLMInputBuilder 替代原有的 CRUD 读取和构建逻辑。
        """
        self.chat_id = chat_id

        system_prompt = (
            "你是一个对话标题生成器。请根据以下对话内容, "
            "为其生成一个简洁、精确、不超过12个字[len(title)<12]的标题。"
            "请仅以JSON格式返回, 格式为: {\"title\": \"生成的标题\"}"
        )

        trigger_prompt = "请根据上述对话内容，输出标题json。"

        # 初始化构建器
        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)

        # 配置构建器：
        # 1. 优先使用全局配置的标题生成模型，其次是默认模型
        # 2. 覆盖 System Prompt
        # 3. 仅截取头尾各2条消息作为摘要依据
        # 4. 限制单条消息内容长度，防止长文涌入
        # 5. 禁用 ZipHistory (标题生成不需要递归处理历史压缩)
        # 6. 将历史聚合为单条 User 消息
        # 7. 追加触发提示词
        llm_input = await (
            builder
            .use_global_model(["title_generation_model_id", "default_model_id"])
            .set_system_prompt(system_prompt)
            .slice_head_tail(head=2, tail=2)
            .limit_sub_message_content(max_length=500)
            .disable_zip_history()
            .filter_sub_message_types(SubMessageType.NORMAL)
            .flatten_history_to_single_user_message()
            .append_user_message(trigger_prompt)
            .build()
        )

        # 强制覆盖特定参数
        llm_input.set_parameter('response_format', {'type': 'json_object'})
        llm_input.set_parameter('stream', False)

        return llm_input

    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将Worker的输出翻译成更新会话名称的指令。
        覆盖 SimpleChatGenerateManager 的默认行为。
        """
        if self.error_occurred:
            return

        if output.type == "content":
            try:
                data = json.loads(output.content)
                title = data.get("title")
                if isinstance(title, str) and 0 < len(title) <= 24:
                    yield UpdateChatName(chat_id=self.chat_id, new_name=title.strip())
                else:
                    self.error_occurred = True
                    print(f"[TitleGenerateManager] Invalid title format or length: {title}")

                    yield NotifyUser(
                        category="title_generation_error",
                        context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
                        level="error",
                        message="生成的标题格式无效或长度不符合要求"
                    )
                    yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)
            except json.JSONDecodeError:
                self.error_occurred = True
                print(f"[TitleGenerateManager] Failed to decode JSON from LLM: {output.content}")

                yield NotifyUser(
                    category="title_generation_error",
                    context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
                    level="error",
                    message="模型返回的标题格式解析失败 (非JSON格式)"
                )
                yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

        elif output.type == "done":
            if not self.error_occurred:
                yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            self.error_occurred = True
            print(f"[TitleGenerateManager] Worker error: {output.content}")

            yield NotifyUser(
                category="title_generation_error",
                context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
                level="error",
                message=f"API调用失败: {output.content}"
            )
            yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas.enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        异常清理逻辑：记录日志并发送全局通知。
        """
        # 产出错误通知
        if exception:
            yield NotifyUser(
                category="title_generation_error",
                context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
                level="error",
                message=f"生成标题时发生系统异常: {str(exception)}"
            )

        # 记录日志
        print(f"[TitleGenerateManager] Cleanup for task '{assistant_message_id}' with status {final_status.value}.")
        if exception:
            print(f"Exception details: {exception}")
