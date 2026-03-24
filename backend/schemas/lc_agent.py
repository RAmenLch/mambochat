import operator
from typing import TypedDict, Annotated

from langchain.agents import AgentState


def replace_reducer(existing, new):
    return new

class MamboAgentState(AgentState):
    files: Annotated[list, operator.add]