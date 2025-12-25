# backend/services/generation/zip_history_manager.py
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.simple_manager import SimpleChatGenerateManager
from backend.services.generation.instructions import (
    BaseInstruction,
    UpdateZipHistorySubMessage,
    SetFinalStatus
)
from backend.services.generation.llm_io import LLMInput, WorkerOutput
from backend.services.generation.llm_input_builder import LLMInputBuilder
from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid

DEFAULT_ZIP_HISTORY_PROMPT = (
    "你是一个对话历史压缩工具。请根据用户提供的对话历史，生成一段简洁、精确、信息完整的摘要。"
    "摘要应保留关键信息、问题、答案和上下文。请直接输出摘要文本，不要添加任何额外的解释或标题。"
)


class ZipHistoryGenerateManager(SimpleChatGenerateManager):
    """
    负责为对话历史生成压缩摘要的管理器。
    它准备一个特殊的LLM输入，请求模型生成摘要，然后将结果作为一种新的子消息类型附加到目标消息上。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.target_message_id: Optional[str] = None
        self._accumulated_content: str = ""
        self.sub_message_id: Optional[str] = None  # 用于 ZipHistory 子消息的 ID

    async def _prepare_llm_input(
            self,
            chat_id: str,
            assistant_message_id: str
    ) -> LLMInput:
        """
        准备用于生成历史摘要的LLM输入。
        使用 LLMInputBuilder 替代原有的 CRUD 读取和构建逻辑。
        """
        # 1. 初始化构建器
        builder = LLMInputBuilder(self.db_session, chat_id=chat_id)

        # 2. 预加载素材以获取设置 (替代 setting_crud.get_setting)
        # 注意：_load_materials 是内部方法，此处调用是为了在 build 前获取 settings
        await builder._load_materials()

        # 3. 获取 System Prompt
        system_prompt = builder.settings.get("zip_history_system_prompt")
        if not system_prompt:
            system_prompt = DEFAULT_ZIP_HISTORY_PROMPT

        # 4. 配置构建器
        # slice_until_message: 截断到目标消息之前 (不包含目标消息)
        # 保持默认的 zip_history 逻辑开启，以便基于已有的压缩历史进行增量压缩 (与原逻辑一致)
        llm_input = await (
            builder
            .slice_until_message(self.target_message_id,include_target=True)
            .set_system_prompt(system_prompt)
            .build()
        )

        # 5. 后处理：追加触发提示和参数
        llm_input.messages.append({"role": "user", "content": "请输出历史摘要:"})
        llm_input.set_parameter('stream', False)

        return llm_input

    async def _translate_worker_output_to_instructions(
            self,
            output: WorkerOutput
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        将Worker的输出翻译成更新ZipHistory子消息的指令。
        覆盖 SimpleChatGenerateManager 的默认行为。
        """
        if output.type == "content" and output.content:
            self._accumulated_content += output.content

        elif output.type == "done":
            # 确保有 ID
            if not self.sub_message_id:
                self.sub_message_id = generate_uuid()

            yield UpdateZipHistorySubMessage(
                sub_message_id=self.sub_message_id,
                target_message_id=self.target_message_id,
                content=self._accumulated_content.strip(),
                status=schemas_enums.MessageStatus.COMPLETED
            )
            yield SetFinalStatus(status=schemas_enums.MessageStatus.COMPLETED)

        elif output.type == "error":
            error_message = f"生成历史摘要时出错: {output.content}"
            if not self.sub_message_id:
                self.sub_message_id = generate_uuid()

            yield UpdateZipHistorySubMessage(
                sub_message_id=self.sub_message_id,
                target_message_id=self.target_message_id,
                content=error_message,
                status=schemas_enums.MessageStatus.FAILED
            )
            # 这里抛出异常以便触发清理逻辑或直接结束
            raise RuntimeError(error_message)

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

    async def run(
            self,
            worker: 'AbstractGenerateWorker',
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        重写 run 方法。
        记录 target_message_id。
        """
        self.target_message_id = assistant_message_id

        # 执行基类的生成流程
        async for instruction in super().run(worker, chat_id, assistant_message_id):
            yield instruction
