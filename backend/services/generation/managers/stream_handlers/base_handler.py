from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, List, Dict, Set, Optional, Any

from langchain_core.tools import BaseTool

from backend.services.generation.core.instructions import BaseInstruction
from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.worker.decode import BaseDecode


@dataclass
class StreamContext:
    """
    流处理上下文。
    在 Manager 和各个 Handler 之间共享状态，避免方法参数过长。
    """
    decode: type[BaseDecode]
    mode: str
    event: Any
    lc_run_uuid: Optional[str]

    # 只读配置
    providers: List[BaseToolProvider]
    tool_map: Dict[str, BaseTool]
    hitl_config: Dict[str, bool]

    # 可变状态 (Handler 可以修改这些状态，Manager 会读取)
    created_stream_ids: Set[str]
    pending_hitl_tool_calls: list
    final_usage_data: dict
    should_interrupt: bool = False


class BaseStreamHandler(ABC):
    """流事件处理器抽象基类"""

    @abstractmethod
    async def handle(self, context: StreamContext) -> AsyncGenerator[BaseInstruction, None]:
        """
        处理具体的流事件。
        如果该事件不属于本 Handler 负责，直接 return/yield 即可。
        """
        if False:
            yield
