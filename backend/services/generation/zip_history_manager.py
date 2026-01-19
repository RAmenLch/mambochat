from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid
from backend.services.generation.instructions import (
    BaseInstruction,
    UpdateZipHistorySubMessage,
    SetFinalStatus
)
from backend.services.generation.abstract_manager import AbstractGenerateManager
from services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend.services.generation.utils import OpenAiDecode

DEFAULT_ZIP_HISTORY_PROMPT = (
    "你是一个对话历史压缩工具。请根据用户提供的对话历史，生成一段简洁、精确、信息完整的摘要。"
    "摘要应保留关键信息、问题、答案和上下文。请直接输出摘要文本，不要添加任何额外的解释或标题。"
)


class ZipHistoryGenerateManager(AbstractGenerateManager):
    """
    V2 历史压缩管理器。
    负责为对话历史生成压缩摘要。
    配置 Builder 截取目标消息之前的历史，调用 Worker 生成摘要文本，并更新 ZipHistory 子消息。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.target_message_id: Optional[str] = None
        self.sub_message_id: Optional[str] = None  # 用于 ZipHistory 子消息的 ID

    async def _execute_generation(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        self.target_message_id = assistant_message_id

        # 1. 初始化构建器
        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)

        # 2. 预加载素材以获取设置
        await builder._load_materials()

        # 3. 获取 System Prompt
        system_prompt = builder.settings.get("zip_history_system_prompt")
        if not system_prompt:
            system_prompt = DEFAULT_ZIP_HISTORY_PROMPT

        # 4. 配置构建器
        # slice_until_message: 截断到目标消息之前 (不包含目标消息)
        # 保持默认的 zip_history 逻辑开启，以便基于已有的压缩历史进行增量压缩
        llm_input = await (
            builder
            .slice_until_message(self.target_message_id, include_target=True)
            .set_system_prompt(system_prompt)
            .build()
        )

        # 5. 后处理：追加触发提示
        # 由于 LLMInputBuilderV2 生成的是 payload 列表，直接操作 messages 列表
        llm_input.messages.append({"role": "user", "content": "请输出历史摘要:"})

        # 6. 执行生成并累积结果
        accumulated_content = ""

        async for mode, event in worker.generate(llm_input):
            text_chunk = OpenAiDecode.get_text_content(mode, event)
            if text_chunk:
                accumulated_content += text_chunk

        # 7. 生成更新指令
        if accumulated_content:
            # 确保有 ID
            if not self.sub_message_id:
                self.sub_message_id = generate_uuid()

            yield UpdateZipHistorySubMessage(
                sub_message_id=self.sub_message_id,
                target_message_id=self.target_message_id,
                content=accumulated_content.strip(),
                status=schemas_enums.MessageStatus.COMPLETED
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)
        else:
            raise RuntimeError("模型未返回任何摘要内容")

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas_enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        在发生未捕获的异常时，创建一个表示失败的ZipHistory子消息。
        """
        error_message = f"生成历史摘要时发生内部错误: {str(exception)}"

        # 确保有 ID
        if not self.sub_message_id:
            self.sub_message_id = generate_uuid()

        yield UpdateZipHistorySubMessage(
            sub_message_id=self.sub_message_id,
            target_message_id=assistant_message_id,
            content=error_message,
            status=schemas_enums.MessageStatus.FAILED
        )
