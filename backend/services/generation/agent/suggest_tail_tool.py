"""``suggest`` 尾部工具。

把"后续对话建议"以 **SUGGEST 子消息**的形式写入(直接落库 + SSE 推送),由
``TailToolMiddleware`` 在每轮收尾后调用。

与旧实现的差异:不再把它当作主模型可调用的工具 + ``SuggestToolProvider`` 指令 +
``FinishRound`` 软中断;而是把它作为一个普通尾部工具,在工具函数内直接写库/推送。
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from backend import schemas
from backend.crud import message_crud
from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import SubMessageConfig
from backend.services.stream_manager_service import stream_manager

#: 尾部工具名(与触发语中的 ``task`` 取值一致)。
SUGGEST_TOOL_NAME = "suggest"

SUGGEST_TOOL_DESCRIPTION = (
    "在回答结束后,向用户提供后续对话建议文本(默认 3~5 条,语言与用户提问一致)。"
)

#: 尾部队列里建议任务的"具体使用说明"(工具描述覆盖不到的部分)。
SUGGEST_TASK_INSTRUCTION = "结合本轮对话给出后续建议,条数遵循用户要求(默认 3~5 条)"


class SuggestArgs(BaseModel):
    suggest_list: List[str] = Field(
        description="3~5 条后续对话建议文本;语言与用户提问语言一致"
    )


def build_suggest_tool(
    *,
    session_factory: Callable[[], AsyncSession],
    message_id: str,
) -> StructuredTool:
    """构造 ``suggest`` 工具:调用时把建议写入一条 SUGGEST 子消息并推送。

    Args:
        session_factory: 无参可调用,返回一个新的 ``AsyncSession``。
        message_id: 目标父消息(即当前轮的 assistant message)ID。
    """

    async def _suggest(suggest_list: List[str]) -> str:
        content = json.dumps(list(suggest_list), ensure_ascii=False)
        sub_id = generate_uuid()
        async with session_factory() as db:
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=content,
                    sortOrder=99,
                    type=schemas_enums.SubMessageType.SUGGEST.value,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    config=SubMessageConfig(context_participation_length=0),
                ),
                sub_message_id=sub_id,
            )
            payload = schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")
        await stream_manager.publish(message_id, {"type": "create", "sub_message": payload})
        return "ok"

    return StructuredTool.from_function(
        name=SUGGEST_TOOL_NAME,
        description=SUGGEST_TOOL_DESCRIPTION,
        coroutine=_suggest,
        args_schema=SuggestArgs,
        infer_schema=False,
    )


def merge_suggest_into_tail_config(
    cfg: Optional[dict],
    *,
    session_factory: Callable[[], AsyncSession],
    message_id: str,
) -> dict:
    """把 suggest 任务(使用说明) + suggest 工具合并进 ``TailToolMiddleware`` 配置 dict。"""
    cfg = dict(cfg or {})
    tasks = list(cfg.get("tasks") or [])
    tools = list(cfg.get("tools") or [])
    if not any(t.get("name") == SUGGEST_TOOL_NAME for t in tasks):
        tasks.append({"name": SUGGEST_TOOL_NAME, "instruction": SUGGEST_TASK_INSTRUCTION})
    tools.append(build_suggest_tool(session_factory=session_factory, message_id=message_id))
    cfg["tasks"] = tasks
    cfg["tools"] = tools
    return cfg
