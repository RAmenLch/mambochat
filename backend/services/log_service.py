# backend/services/log_service.py

import logging
from typing import Dict, Any, Optional

from backend.database import AsyncSessionLocal
from backend.crud.log_crud import create_post_log

logger = logging.getLogger(__name__)

async def async_save_post_log(
    chat_id: Optional[str],
    message_id: Optional[str],
    manager_name: Optional[str],
    agent_name: Optional[str],
    config_meta_data: Optional[Dict[str, Any]],
    raw_payload: Optional[Dict[str, Any]]
) -> None:
    """
    异步保存底层报文日志到数据库。
    该方法拥有独立的数据库会话生命周期，并且会捕获所有异常以保证主业务流程不受影响。
    """
    try:
        async with AsyncSessionLocal() as db:
            log_data = {
                "chatId": chat_id,
                "messageId": message_id,
                "managerName": manager_name,
                "agentName": agent_name,
                "configMetaData": config_meta_data,
                "rawPayload": raw_payload
            }
            await create_post_log(db, log_data)
    except Exception as e:
        # 仅记录日志，绝对不向上抛出异常 (Fire-and-Forget)
        logger.error(f"Failed to asynchronously save MamboPostLog for message_id {message_id}: {e}", exc_info=True)

