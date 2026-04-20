# backend/services/generation/builders/resource_dispatcher.py

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import resource_crud
from backend.schemas.enums import ResourceType, ResourceItemType
from backend.services.generation.core.llm_io import SkillConfig, SkillFileConfig


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
            "skills": List[SkillConfig]        # 技能包配置列表
        }
        """
        result = {
            "system_prompts": [],
            "submessage_templates": [],
            "knowledge_bases": [],
            "skills": []
        }

        if not resource_ids:
            return result

        # 批量获取资源对象 (包含 latest_version)
        resources = await resource_crud.get_resources_by_ids(self.db, resource_ids)

        # 创建映射以保持原始列表顺序
        resources_map = {res.id: res for res in resources}

        skill_roots = []

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

            elif res.resourceType == ResourceType.SKILL.value:
                # 收集 SKILL 根节点，后续统一处理
                skill_roots.append(res)

        # --- 处理 SKILL 类型的资源 ---
        if skill_roots:
            skill_ids = [r.id for r in skill_roots]
            # 递归获取所有子孙节点
            descendants = await resource_crud.get_skill_descendants_with_versions(self.db, skill_ids)
            node_map = {d.id: d for d in descendants}
            skill_files_map = {r.id: [] for r in skill_roots}

            for node in descendants:
                # 仅处理包含底层文件 ID 的资源节点（忽略纯文件夹）
                if node.itemType == ResourceItemType.RESOURCE.value and node.latest_version and node.latest_version.content:
                    path_parts = [node.name]
                    current_parent_id = node.parentId
                    root_id = None

                    # 向上回溯构建相对路径
                    while current_parent_id:
                        if current_parent_id in skill_files_map:
                            root_id = current_parent_id
                            break
                        parent_node = node_map.get(current_parent_id)
                        if not parent_node:
                            break
                        path_parts.append(parent_node.name)
                        current_parent_id = parent_node.parentId

                    if root_id:
                        root_node = node_map.get(root_id)
                        if root_node:
                            path_parts.append(root_node.name)

                        # 反转路径部分以获得正向层级树 (例如 SKILL_A/src/main.py)
                        path_parts.reverse()
                        relative_path = "/".join(path_parts)

                        file_config = SkillFileConfig(
                            file_path=relative_path,
                            file_id=node.latest_version.content
                        )
                        skill_files_map[root_id].append(file_config)

            # 组装最终的 SkillConfig
            for root in skill_roots:
                skill_config = SkillConfig(
                    name=root.name,
                    files=skill_files_map[root.id]
                )
                result["skills"].append(skill_config)

        return result
