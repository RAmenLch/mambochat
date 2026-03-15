import operator
from typing import TypedDict, Annotated

def replace_reducer(existing, new):
    return new

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    # 使用 Annotated 允许并发写入，reducer 会按顺序处理它们
    intent: Annotated[str, replace_reducer]