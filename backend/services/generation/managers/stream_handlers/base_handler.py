from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Dict, Set, Optional

from langchain_core.tools import BaseTool

from backend.services.generation.core.instructions import BaseInstruction
from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.worker.decode import BaseDecode
from backend.services.generation.worker.abstract_worker import StreamEvent


@dataclass
class StreamContext:
    """
    流处理上下文。
    在 Manager 和各个 Handler 之间共享状态，避免方法参数过长。
    """
    decode: BaseDecode
    mode: str
    event: StreamEvent
    lc_run_uuid: Optional[str]

    # 只读配置
    providers: List[BaseToolProvider]
    tool_map: Dict[str, BaseTool]
    hitl_config: Dict[str, bool]

    # 可变状态 (Handler 可以修改这些状态，Manager 会读取)
    created_stream_ids: Set[str]
    pending_hitl_tool_calls: list
    should_interrupt: bool = False
    last_finish_reason: Optional[str] = None

    # 新增：subagent_event 相关追踪字段
    subagent_step_counters: Dict[str, int] = field(default_factory=dict)

    # 多中断批次追踪：当多个工具并行调用 interrupt() 时，多个 __interrupt__
    # 事件会按 task 逐个发射。此字段让 HitlHandler 在多次 handle() 调用间
    # 共享同一个 batch_id，确保所有中断属于同一批次。
    hitl_batch_id: Optional[str] = None

    # 多中断序号：跨事件递增，确保每个 AskUserContent 有唯一的 interrupt_index
    hitl_interrupt_counter: int = 0


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
