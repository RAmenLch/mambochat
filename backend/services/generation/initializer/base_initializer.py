# backend/services/generation/initializer/base_initializer.py

from abc import ABC, abstractmethod
from typing import Tuple, List

from backend.services.generation.llm_io import AgentConfig
from backend.services.generation.tools.base_tool_provider import BaseToolProvider


class AbstractAgentInitializer(ABC):
    """
    Agent 初始化器抽象基类。
    负责根据不同的业务实体（如 Chat 或独立的 Agent 表）解析配置，
    装配工具链，并生成标准的 AgentConfig。
    """

    @abstractmethod
    async def initialize(self) -> Tuple[AgentConfig, str]:
        """
        执行初始化逻辑。

        Returns:
            Tuple[AgentConfig, str]:
                - AgentConfig: 标准化的 Agent 运行与调度配置。
                - str: 需要追加到 System Prompt 的附加提示词（如资源注入、工具使用说明等）。
        """
        pass

    @abstractmethod
    def get_providers(self) -> List[BaseToolProvider]:
        """
        获取初始化的工具提供者列表。
        供上层 Manager 在解析 Worker 流式事件时，生成对应的 UI 指令。
        """
        pass

