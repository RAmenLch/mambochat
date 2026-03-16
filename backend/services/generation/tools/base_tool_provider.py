from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool
from backend.services.generation.instructions import BaseInstruction


class BaseToolProvider(ABC):
    """
    工具提供者抽象基类。
    负责管理特定类型的工具集合，包括工具的获取、提示词注入以及工具调用/结果的指令生成。
    """

    @abstractmethod
    async def get_tools(self) -> List[BaseTool]:
        """
        获取该提供者管理的所有 LangChain 工具实例。
        可能涉及异步操作（如建立网络连接或查询数据库）。
        """
        pass

    @abstractmethod
    def get_system_prompt_injection(self) -> Optional[str]:
        """
        获取需要注入到 System Prompt 的额外提示词。
        用于指导 LLM 如何使用这些工具。
        """
        pass

    @abstractmethod
    def matches_tool_name(self, tool_name: str) -> bool:
        """
        判断给定的工具名称是否属于该提供者管理。
        """
        pass

    @abstractmethod
    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        当 LLM 发起工具调用时，生成对应的 UI 创建指令。
        例如创建 MCP_TOOL 或 SUGGEST 类型的子消息。
        """
        if False:
            yield

    @abstractmethod
    async def create_result_instruction(
        self,
        tool_call_id: str,
        result_text: str,
        is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        当工具执行完毕获得结果时，生成对应的 UI 更新指令。
        例如更新子消息的内容和状态。
        """
        if False:
            yield
