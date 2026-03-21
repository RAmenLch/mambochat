# backend/services/generation/builders/initializers/chat_react_initializer.py

import json
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.schemas.enums import ToolReviewMode, AgentTypeEnum
from backend.crud import mcp_crud

# 导入核心层和同级组件
from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.builders.initializers.base_initializer import AbstractAgentInitializer
from backend.services.generation.builders.resource_dispatcher import ResourceDispatcher

# 导入工具 Provider
from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mcp_tool_provider import MCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider
from backend.services.generation.tools.kb_tool_provider import KBToolProvider


class ChatBasedReActInitializer(AbstractAgentInitializer):
    """
    基于 Chat 表配置的 ReAct Agent 初始化器。
    负责提取 Chat 表中的工具与资源装配逻辑，生成 AgentConfig。
    """

    def __init__(
            self,
            db: AsyncSession,
            chat: Any,  # 数据库 Chat 模型实例
            thread_id: str,
            resume_payload: Optional[Dict[str, Any]] = None,
            enable_tools: bool = False,
            enable_resource_merge: bool = False,
            external_tools: Optional[List[BaseTool]] = None
    ):
        self.db = db
        self.chat = chat
        self.thread_id = thread_id
        self.resume_payload = resume_payload
        self.enable_tools = enable_tools
        self.enable_resource_merge = enable_resource_merge
        self.external_tools = external_tools or []

        self.providers: List[BaseToolProvider] = []
        self.hitl_interrupt_on: Dict[str, bool] = {}

    async def initialize(self) -> Tuple[AgentConfig, str]:
        extended_prompts: List[str] = []
        knowledge_bases = []
        skills = []

        # 1. 资源挂载与分发 (从 Chat 表读取 resource_prompt_list)
        if self.enable_resource_merge and self.chat.resource_prompt_list:
            dispatcher = ResourceDispatcher(self.db)
            dispatch_result = await dispatcher.dispatch(self.chat.resource_prompt_list)

            for content in dispatch_result.get("system_prompts", []):
                extended_prompts.append(content)
            for content in dispatch_result.get("submessage_templates", []):
                extended_prompts.append(content)

            knowledge_bases = dispatch_result.get("knowledge_bases", [])
            skills = dispatch_result.get("skills", [])

        # 挂载知识库工具
        if knowledge_bases:
            self.providers.append(KBToolProvider(self.db, knowledge_bases))

        # 2. 外部工具挂载 (MCP & Suggest)
        if self.enable_tools:
            params = {}
            if self.chat and self.chat.modelParameters:
                try:
                    params = json.loads(self.chat.modelParameters) if isinstance(self.chat.modelParameters, str) else self.chat.modelParameters
                except (json.JSONDecodeError, TypeError):
                    pass

            # MCP 服务 (从 Chat 表读取 enabled_mcp_ids)
            mcp_ids = self.chat.enabled_mcp_ids or []
            if mcp_ids:
                self.providers.append(MCPToolProvider(self.db, mcp_ids))

                # 提取 HITL 审核配置
                mcp_tools = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                for tool in mcp_tools:
                    if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                        self.hitl_interrupt_on[tool.name] = True

            # Suggest 建议工具 (从 Chat 的 modelParameters 中读取)
            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

        # 3. 收集所有工具实例与 Provider 的提示词注入
        all_tools: List[BaseTool] = list(self.external_tools)
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)

        # 4. 构建 AgentConfig
        # Chat 模式默认固定使用 REACT 类型的 Agent
        agent_config = AgentConfig(
            agent_type=AgentTypeEnum.REACT,
            tools=all_tools if all_tools else None,
            skills=skills if skills else None,
            hitl_interrupt_on=self.hitl_interrupt_on,
            thread_id=self.thread_id,
            resume_payload=self.resume_payload
        )

        # 5. 合并附加的 System Prompt
        additional_system_prompt = "\n\n".join(extended_prompts) if extended_prompts else ""

        return agent_config, additional_system_prompt

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers

