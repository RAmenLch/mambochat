# backend/services/generation/tools/kb_tool_provider.py

import json
from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.kb_service import KnowledgeBaseService
from backend.schemas import enums as schemas_enums
from backend.schemas.kb import KBSearchRequest
from backend.schemas.message import McpToolContent
from backend.models.base_model import generate_uuid
from backend.crud import kb_crud, resource_crud
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus
)


class KBToolProvider(BaseToolProvider):
    """
    Native 知识库工具提供者。
    将知识库检索能力封装为内部原生工具，消除对外部 MCP 进程的依赖。
    前端交互复用 MCP_TOOL 协议，保持体验一致性。
    """

    def __init__(self, db_session: AsyncSession, kb_resources: List[Any]):
        """
        :param db_session: 数据库会话
        :param kb_resources: 已挂载的知识库资源对象列表 (ORM 对象列表)
        """
        self.db_session = db_session
        self.kb_resources = kb_resources
        self._tool_name_search = "search_knowledge_base"
        self._tool_name_chunks = "get_kb_chunks"
        self._tool_name_regex = "search_kb_by_regex"

        # 状态映射：tool_call_id -> sub_message_id
        self._tool_sub_msg_map: Dict[str, str] = {}
        # 工具信息缓存：tool_call_id -> McpToolContent
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        if not self.kb_resources:
            return []

        # 捕获 self 以便在闭包内使用
        provider_self = self

        @tool(provider_self._tool_name_search)
        async def search_knowledge_base(query: str, kb_name: str, top_k: int = 5) -> str:
            """
            在指定的知识库中检索相关信息。
            query: 检索关键词或问题。
            kb_name: 知识库的名称，必须从系统提示词提供的列表中选择。
            top_k: 返回的最相似结果数量，默认5。
            """
            # 1. 查找目标知识库
            target_resource = None
            for res in provider_self.kb_resources:
                if res.name == kb_name:
                    target_resource = res
                    break

            if not target_resource:
                available_names = [res.name for res in provider_self.kb_resources]
                return f"Error: Knowledge base '{kb_name}' not found. Available: {', '.join(available_names)}"

            # 2. 调用检索服务
            service = KnowledgeBaseService(provider_self.db_session)
            request = KBSearchRequest(
                query_text=query,
                kb_id=target_resource.id,
                top_k=top_k
            )

            try:
                response = await service.search_kb(request)
                if not response.items:
                    return "No relevant information found."

                # 格式化结果
                results_text = []
                for item in response.items:
                    results_text.append(
                        f"Source: {item.resource_name}\nContent: {item.chunk_content}"
                    )
                return "\n\n---\n\n".join(results_text)
            except Exception as e:
                return f"Search failed: {str(e)}"

        @tool(provider_self._tool_name_chunks)
        async def get_kb_chunks(resource_name: str, start_index: int, end_index: int, page: int = 1, page_size: int = 5) -> str:
            """
            通过文件名和切片索引范围查询知识库切片内容，用于RAG检索后进一步阅读上下文。
            resource_name: 知识库中的文件名称（如 xxx.txt），不是知识库名称。
            start_index: 切片索引起始值 (包含)，从0开始。
            end_index: 切片索引结束值 (包含)。
            page: 页码，默认1。
            page_size: 每页数量，默认5。
            """
            # 1. 在已挂载的知识库中查找目标文件资源
            kb_ids = [res.id for res in provider_self.kb_resources]
            target_resource = await resource_crud.get_file_resource_by_name_and_kb_ids(
                provider_self.db_session, resource_name, kb_ids
            )

            if not target_resource:
                # 列出所有可用文件名供参考
                all_files = await resource_crud.get_file_resources_by_kb_ids(
                    provider_self.db_session, kb_ids
                )
                available_names = [f.name for f in all_files]
                return f"Error: File '{resource_name}' not found in mounted knowledge bases. Available files: {', '.join(available_names)}"

            # 2. 查询切片
            try:
                chunks, total = await kb_crud.get_chunks_by_resource_paginated(
                    db=provider_self.db_session,
                    resource_id=target_resource.id,
                    min_index=start_index,
                    max_index=end_index,
                    page=page,
                    page_size=page_size
                )

                if not chunks:
                    return f"No chunks found in range [{start_index}, {end_index}]."

                results_text = []
                for chunk in chunks:
                    results_text.append(
                        f"[Chunk {chunk.chunk_index}]\n{chunk.content}"
                    )
                return f"Total: {total}\n\n" + "\n\n---\n\n".join(results_text)
            except Exception as e:
                return f"Get chunks failed: {str(e)}"

        @tool(provider_self._tool_name_regex)
        async def search_kb_by_regex(pattern: str, kb_name: str = "", page: int = 1, page_size: int = 5) -> str:
            """
            使用正则表达式在知识库切片内容中搜索。支持Python re模块正则语法。
            pattern: 正则表达式模式，例如 '第\\d+章' 或 'import\\s+\\w+'。
            kb_name: 限定搜索的知识库名称，为空则搜索所有已挂载的知识库。
            page: 页码，默认1。
            page_size: 每页数量，默认5。
            """
            # 1. 确定搜索范围
            kb_id = None
            if kb_name:
                target_resource = None
                for res in provider_self.kb_resources:
                    if res.name == kb_name:
                        target_resource = res
                        break

                if not target_resource:
                    available_names = [res.name for res in provider_self.kb_resources]
                    return f"Error: Knowledge base '{kb_name}' not found. Available: {', '.join(available_names)}"
                kb_id = target_resource.id

            # 2. 执行正则搜索
            try:
                rows, total = await kb_crud.search_chunks_by_regex(
                    db=provider_self.db_session,
                    pattern=pattern,
                    kb_id=kb_id,
                    page=page,
                    page_size=page_size
                )

                if not rows:
                    return f"No matches found for pattern: {pattern}"

                results_text = []
                for row in rows:
                    results_text.append(
                        f"Source: {row.resource_name} [Chunk {row.chunk_index}]\nContent: {row.chunk_content}"
                    )
                return f"Total: {total}\n\n" + "\n\n---\n\n".join(results_text)
            except Exception as e:
                return f"Regex search failed: {str(e)}"

        return [search_knowledge_base, get_kb_chunks, search_kb_by_regex]

    def get_system_prompt_injection(self) -> Optional[str]:
        if not self.kb_resources:
            return None

        # 构建知识库列表描述
        kb_list_desc = []
        for res in self.kb_resources:
            desc = res.description or "No description"
            kb_list_desc.append(f"- Name: {res.name}, Description: {desc}")

        kb_info_str = "\n".join(kb_list_desc)

        return (
            f"You have access to the following knowledge bases for background information:\n"
            f"{kb_info_str}\n"
            f"Use the '{self._tool_name_search}' tool to search them by semantic similarity. You MUST specify the correct 'kb_name' (the name of a knowledge base, not a file name).\n"
            f"Use the '{self._tool_name_chunks}' tool to read chunk content by index range when you need more context around a search result. 'resource_name' is the file name (e.g. 'document.txt') within the knowledge base, NOT the knowledge base name.\n"
            f"Use the '{self._tool_name_regex}' tool to search by regular expression pattern when you need precise text matching. You can optionally specify 'kb_name' to limit scope."
        )

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in (self._tool_name_search, self._tool_name_chunks, self._tool_name_regex)

    async def create_call_instruction(
            self,
            tool_call_id: str,
            name: str,
            arguments: Dict[str, Any],
            tool_def: Optional[BaseTool] = None  # 适配新签名
    ) -> AsyncGenerator[BaseInstruction, None]:
        # 1. 提取原生工具定义中的 Schema
        input_schema = tool_def.args if tool_def else None

        # 2. 构建 McpToolContent 对象 (复用 MCP 数据结构以保持协议一致)
        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema  # 注入 Schema
        )

        # 3. 缓存状态
        self._tool_info_cache[tool_call_id] = tool_content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        # 4. 生成创建子消息指令
        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=tool_content.to_json_string(),
            config={"is_minimal": True}
        )

    async def create_result_instruction(
            self,
            tool_call_id: str,
            result_text: str,
            is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:
        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        if sub_id and cached_content:
            # 更新缓存对象的状态
            cached_content.result = result_text
            cached_content.is_error = is_error

            # 发送全量更新指令
            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string()
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )

    def restore_state(self, tool_call_id: str, sub_message_id: str, tool_content: Any) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content

