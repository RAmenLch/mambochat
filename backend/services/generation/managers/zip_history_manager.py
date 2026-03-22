# backend/services/generation/managers/zip_history_manager.py

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid

# 1. 导入核心层指令
from backend.services.generation.core.instructions import (
    BaseInstruction,
    UpdateZipHistorySubMessage,
    SetFinalStatus
)

# 2. 导入抽象基类和 Worker
from backend.services.generation.managers.base_manager import AbstractGenerateManager
from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker

# 3. 导入装配层的 Director 和 Loader
from backend.services.generation.builders.director import LLMInputDirector
from backend.services.generation.builders.material_loader import GenerationMaterialLoader

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

        # 1. 使用独立的 Loader 获取物料 (替代原先的 director._load_materials)
        materials = await GenerationMaterialLoader.load(self.db_session, chat_id)
        settings = materials.settings

        # 2. 获取 System Prompt
        system_prompt = settings.get("zip_history_system_prompt")
        if not system_prompt:
            system_prompt = DEFAULT_ZIP_HISTORY_PROMPT

        # 3. 初始化并配置指挥官
        director = LLMInputDirector(self.db_session, chat_id=chat_id)

        # slice_until_message: 截断到目标消息之前 (包含目标消息用于上下文)
        llm_input = await (
            director
            .force_normal_mode()
            .slice_until_message(self.target_message_id, include_target=True)
            .filter_sub_message_types(schemas_enums.SubMessageType.NORMAL.value)
            .set_system_prompt(system_prompt)
            .build()
        )

        language = settings.get("language")
        en_prompt = "Please output a summary of the conversation history:"
        cn_prompt = "请输出历史摘要:"
        prompt = cn_prompt if language == "zh-CN" else en_prompt

        # 4. 后处理：追加触发提示
        # 适配新架构：将消息追加到 context.messages 中
        llm_input.context.messages.append({"role": "user", "content": prompt})

        # 5. 执行生成并累积结果
        accumulated_content = ""

        async for mode, event in worker.generate(llm_input):
            text_chunk = self.decode.get_text_content(mode, event)
            if text_chunk:
                accumulated_content += text_chunk

        # 6. 生成更新指令
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
