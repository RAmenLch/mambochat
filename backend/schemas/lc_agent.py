from typing import TypedDict, Optional

from backend.services.generation.core.llm_io import RunTimeConfig


class MamboContext(TypedDict):
    chat_id:str
    manager_name:Optional[str]
    message_id:Optional[str]