import json
from typing import AsyncGenerator, Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.schemas import SubMessageType
from backend.services.generation.instructions import (
    BaseInstruction,
    SetFinalStatus,
    UpdateChatName,
    NotifyUser
)
from backend.services.generationv2.abstract_manager import AbstractGenerateManager
from backend.services.generationv2.base import AbstractGenerateWorker
from backend.services.generationv2.llm_input_builder import LLMInputBuilderV2
from backend.services.generationv2.utils import OpenAiDecode


class TitleGenerationContext(BaseModel):
    """标题生成任务的上下文信息"""
    chat_id: str


class TitleGenerateManager(AbstractGenerateManager):
    """
    V2 标题生成管理器。
    负责为会话自动生成标题。
    配置 Builder 提取摘要上下文，调用 Worker 生成 JSON 格式标题，并解析结果更新会话名称。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.chat_id: Optional[str] = None

    async def _execute_generation(
            self,
            worker: AbstractGenerateWorker,
            chat_id: str,
            assistant_message_id: str
    ) -> AsyncGenerator[BaseInstruction, None]:

        self.chat_id = chat_id

        # 1. 准备提示词
        system_prompt = (
            "你是一个对话标题生成器。请根据以下对话内容, "
            "为其生成一个简洁、精确、不超过12个字[len(title)<12]的标题。"
            "请仅以JSON格式返回, 格式为: {\"title\": \"生成的标题\"}"
        )
        trigger_prompt = "请根据上述对话内容，输出标题json。"

        # 2. 初始化构建器
        builder = LLMInputBuilderV2(self.db_session, chat_id=chat_id)

        # 3. 配置构建器 (保持与 V1 逻辑一致)
        # - 优先使用全局配置的标题生成模型
        # - 仅截取头尾各2条消息
        # - 限制内容长度
        # - 禁用 ZipHistory
        # - 聚合历史为单条 User 消息
        llm_input = await (
            builder
            .use_global_model(["title_generation_model_id", "default_model_id"])
            .set_system_prompt(system_prompt)
            .slice_head_tail(head=2, tail=2)
            .limit_sub_message_content(max_length=500)
            .disable_zip_history()
            .filter_sub_message_types(SubMessageType.NORMAL.value)
            .flatten_history_to_single_user_message()
            .append_user_message(trigger_prompt)
            .build()
        )

        # 强制 JSON 模式
        llm_input.set_parameter('response_format', {'type': 'json_object'})

        # 4. 执行生成并累积结果
        accumulated_content = ""

        async for mode, event in worker.generate(llm_input):
            text_chunk = OpenAiDecode.get_text_content(mode, event)
            if text_chunk:
                accumulated_content += text_chunk

        # 5. 解析结果
        if accumulated_content:
            try:
                data = json.loads(accumulated_content)
                title = data.get("title")

                if isinstance(title, str) and 0 < len(title) <= 24:
                    yield UpdateChatName(chat_id=self.chat_id, new_name=title.strip())
                    yield SetFinalStatus(status=schemas.enums.MessageStatus.COMPLETED)
                else:
                    yield self._create_error_notification("生成的标题格式无效或长度不符合要求")
                    yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

            except json.JSONDecodeError:
                yield self._create_error_notification("模型返回的标题格式解析失败 (非JSON格式)")
                yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)
        else:
            yield self._create_error_notification("模型未返回任何内容")
            yield SetFinalStatus(status=schemas.enums.MessageStatus.FAILED)

    def _create_error_notification(self, message: str) -> NotifyUser:
        """辅助方法：创建错误通知指令"""
        return NotifyUser(
            category="title_generation_error",
            context=TitleGenerationContext(chat_id=self.chat_id or "unknown"),
            level="error",
            message=message
        )

    async def _cleanup_on_exception(
            self,
            assistant_message_id: str,
            final_status: schemas.enums.MessageStatus,
            exception: Optional[Exception] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        异常清理逻辑：发送全局通知。
        """
        if exception:
            yield self._create_error_notification(f"生成标题时发生系统异常: {str(exception)}")
