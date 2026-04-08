# backend/services/generation/builders/material_loader.py

from dataclasses import dataclass
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import TypeAdapter

from backend.crud import chat_crud, message_crud, setting_crud, agent_crud
from backend.schemas.enums import ChatMode
from backend.models.chat_model import Chat
from backend.models.agent_model import Agent
from backend.services.generation.core.llm_io import MessageSchema

_message_adapter: TypeAdapter[List[MessageSchema]] = TypeAdapter(List[MessageSchema])


@dataclass
class GenerationMaterials:
    """承载从数据库加载的基础物料数据结构"""
    chat: Chat
    history: List[MessageSchema]
    settings: Dict[str, str]
    target_msg: Optional[MessageSchema] = None
    agent: Optional[Agent] = None


class GenerationMaterialLoader:
    """
    生成物料加载器。
    负责从数据库中提取 Chat、Agent、History 和 Settings，并处理截断 (Cutoff) 逻辑。
    在数据加载边界处统一将 ORM Message 转换为 MessageSchema。
    """

    @staticmethod
    async def load(
            db: AsyncSession,
            chat_id: str,
            cutoff_message_id: Optional[str] = None,
            cutoff_include: bool = False,
            history_override: Optional[List[MessageSchema]] = None
    ) -> GenerationMaterials:

        # 1. 加载 Chat
        chat = await chat_crud.get_chat(db, chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not found.")

        # 1.5 加载 Agent (如果会话模式为 Agent 且绑定了有效的 AgentId)
        agent = None
        if chat.chatMode == ChatMode.AGENT.value and chat.agentId:
            agent = await agent_crud.get_agent(db, chat.agentId)

        # 2. 加载全局设置
        all_settings = await setting_crud.get_all_settings(db)
        settings = {s.key: s.value for s in all_settings}

        # 3. 加载并处理历史消息
        history: List[MessageSchema] = []
        target_msg: Optional[MessageSchema] = None

        if history_override is not None:
            history = history_override
            if cutoff_message_id:
                target_msg = next((m for m in history if m.id == cutoff_message_id), None)
        else:
            all_msgs = await message_crud.get_messages_by_chat(db, chat_id)
            if cutoff_message_id:
                try:
                    idx = next(i for i, m in enumerate(all_msgs) if m.id == cutoff_message_id)
                    target_msg = MessageSchema.model_validate(all_msgs[idx])
                    end_index = idx + 1 if cutoff_include else idx
                    history = _message_adapter.validate_python(all_msgs[:end_index])
                except StopIteration:
                    history = _message_adapter.validate_python(all_msgs)
            else:
                history = _message_adapter.validate_python(all_msgs)

        # 4. 组装并返回所有基础物料
        return GenerationMaterials(
            chat=chat,
            history=history,
            settings=settings,
            target_msg=target_msg,
            agent=agent
        )
