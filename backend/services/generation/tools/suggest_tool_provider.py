import json
from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool, tool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.instructions import (
    BaseInstruction,
    CreateSubMessage, InterruptGeneration
)
from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid


class SuggestToolProvider(BaseToolProvider):
    """
    建议 (Suggest) 工具提供者。
    提供一个虚拟工具，允许 LLM 在回复末尾输出后续对话建议。
    """

    def __init__(self, enable_suggest: bool):
        self.enable_suggest = enable_suggest
        self._tool_name = "suggest"

    async def get_tools(self) -> List[BaseTool]:
        if not self.enable_suggest:
            return []

        @tool(self._tool_name)
        def suggest(suggest_list: List[str]) -> str:
            """
            请在输出所有完整文本之后,可调用此方法,提供3~5个建议文本选项给用户选择,建议文本内容语言取决于用户提问的语言;
            """
            return "ok"

        return [suggest]

    def get_system_prompt_injection(self) -> Optional[str]:
        if not self.enable_suggest:
            return None

        return (
            "在生成正文结束后,如果你对用户有回复推荐,请调用suggest方法。"
        )

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name == self._tool_name

    async def create_call_instruction(
            self,
            tool_call_id: str,
            name: str,
            arguments: Dict[str, Any]
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        解析 suggest 工具调用，生成 SUGGEST 类型的子消息。
        """
        suggest_list = arguments.get("suggest_list", [])

        # 确保是列表格式
        if not isinstance(suggest_list, list):
            # 尝试兼容处理，如果 LLM 传错了格式
            if isinstance(suggest_list, str):
                suggest_list = [suggest_list]
            else:
                suggest_list = []

        # 序列化建议列表
        content_json = json.dumps(suggest_list, ensure_ascii=False)
        sub_id = generate_uuid()

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.SUGGEST.value,
            sortOrder=99,  # 建议通常放在最后
            status=schemas_enums.MessageStatus.COMPLETED,
            initial_content=content_json,
            config={"context_participation_length": 0}
        )
        yield InterruptGeneration()

    async def create_result_instruction(
            self,
            tool_call_id: str,
            result_text: str,
            is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:
        # Suggest 工具不需要在 UI 上展示执行结果（"ok"），也不需要更新状态
        # 因为 CreateSubMessage 时状态已经是 COMPLETED
        if False:
            yield
