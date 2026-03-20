# backend/services/generation/builders/material_loader.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import chat_crud, message_crud, setting_crud


@dataclass
class GenerationMaterials:
    """承载从数据库加载的基础物料数据结构"""
    chat: Any
    history: List[Any]
    settings: Dict[str, str]
    target_msg: Optional[Any] = None


class GenerationMaterialLoader:
    """
    生成物料加载器。
    负责从数据库中提取 Chat、History 和 Settings，并处理截断 (Cutoff) 逻辑。
    """

    @staticmethod
    async def load(
            db: AsyncSession,
            chat_id: str,
            cutoff_message_id: Optional[str] = None,
            cutoff_include: bool = False,
            history_override: Optional[List[Any]] = None
    ) -> GenerationMaterials:

        # 1. 加载 Chat
        chat = await chat_crud.get_chat(db, chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not found.")

        # 2. 加载全局设置
        all_settings = await setting_crud.get_all_settings(db)
        settings = {s.key: s.value for s in all_settings}

        # 3. 加载并处理历史消息
        history = []
        target_msg = None

        if history_override is not None:
            history = history_override
            if cutoff_message_id:
                target_msg = next((m for m in history if getattr(m, 'id', None) == cutoff_message_id), None)
        else:
            all_msgs = await message_crud.get_messages_by_chat(db, chat_id)
            if cutoff_message_id:
                try:
                    idx = next(i for i, m in enumerate(all_msgs) if m.id == cutoff_message_id)
                    target_msg = all_msgs[idx]
                    end_index = idx + 1 if cutoff_include else idx
                    history = all_msgs[:end_index]
                except StopIteration:
                    history = all_msgs
            else:
                history = all_msgs

        return GenerationMaterials(
            chat=chat,
            history=history,
            settings=settings,
            target_msg=target_msg
        )
