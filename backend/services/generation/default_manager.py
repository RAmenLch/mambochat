# backend/services/generation/default_manager.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.react_manager import ReActAgentChatGenerateManager
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage,
    AppendToSubMessage,
    SaveAndPersistFile
)
from backend.services.generation.llm_io import WorkerOutput
from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid


class DefaultGenerateManager(ReActAgentChatGenerateManager):
    """
    默认生成管理器，负责根据聊天记录准备LLM输入（包括处理图片、文本文件和已启用的压缩历史）。
    继承自 ReActAgentChatGenerateManager，因此原生支持工具调用和 ReAct 循环。
    扩展了对 generated image 输出的处理。
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)

    # 注意：_prepare_llm_input 的逻辑已完全移至父类 ReActAgentChatGenerateManager 中，
    # 结合 LLMInputBuilder 实现。
    # LLMInputBuilder 已内置了多模态处理、ZipHistory逻辑、CPL过滤、Proxy配置及参数映射，
    # 覆盖了原 DefaultGenerateManager 的所有输入构建需求。

    async def _handle_custom_worker_output(self, output: WorkerOutput) -> AsyncGenerator[BaseInstruction, None]:
        """
        处理基类不支持的自定义输出类型，例如生成的图片。
        不再执行IO操作，而是发出 SaveAndPersistFile 指令交由 Executor 处理。
        """
        if output.type == "image_content":
            try:
                # 解析 Base64 数据字符串
                # 格式通常为: data:image/png;base64,iVBORw0KGgo...
                if ',' in output.content:
                    header, encoded_data = output.content.split(',', 1)
                    mime_type = header.split(';')[0].split(':')[1]
                else:
                    # 容错处理
                    encoded_data = output.content
                    mime_type = "image/png"

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
