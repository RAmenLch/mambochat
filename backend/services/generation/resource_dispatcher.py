# backend/services/generation/resource_dispatcher.py

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import resource_crud
from backend.schemas.enums import ResourceType


class ResourceDispatcher:
    """
    资源分发器。
    负责根据 ID 列表加载资源，并按类型进行分类路由。
    保持资源的原始挂载顺序。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def dispatch(self, resource_ids: List[str]) -> Dict[str, Any]:
        """
        获取并分类资源。

        返回结构:
        {
            "system_prompts": List[str],       # 系统提示词内容列表
            "submessage_templates": List[str], # 子消息模板内容列表
            "knowledge_bases": List[Any],      # 知识库资源对象列表 (ORM 对象)
        }
        """
        result = {
            "system_prompts": [],
            "submessage_templates": [],
            "knowledge_bases": []
        }

        if not resource_ids:
            return result

        # 批量获取资源对象 (包含 latest_version)
        resources = await resource_crud.get_resources_by_ids(self.db, resource_ids)

        # 创建映射以保持原始列表顺序
        resources_map = {res.id: res for res in resources}

        for rid in resource_ids:
            res = resources_map.get(rid)
            if not res:
                continue

            # 提取内容
            content = res.latest_version.content if res.latest_version else None

            if res.resourceType == ResourceType.SYSTEM_PROMPT.value:
                if content:
                    result["system_prompts"].append(content)

            elif res.resourceType == ResourceType.SUBMESSAGE_TEMPLATE.value:
                if content:
                    result["submessage_templates"].append(content)

            elif res.resourceType == ResourceType.KNOWLEDGE_BASE.value:
                # 知识库需要传递完整的 ORM 对象，以便 KBToolProvider 获取名称、描述和 ID
                result["knowledge_bases"].append(res)

            # FILE, SKILL 等类型当前阶段忽略，保留未来扩展接口

        return result
