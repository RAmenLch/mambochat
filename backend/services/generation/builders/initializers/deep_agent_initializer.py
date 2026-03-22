# backend/services/generation/builders/initializers/deep_agent_initializer.py

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
from backend.services.generation.tools.deep_builtin_tool_provider import DeepAgentBuiltinToolProvider
from backend.services.file_service import FileService


class DeepAgentInitializer(AbstractAgentInitializer):
    """
    针对 DeepAgent 架构的初始化器。
    解析数据库配置，提取技能库 (Skills) 路径与工具，生成标准化的 AgentConfig。
    不将技能库内容硬编码拼接到 system_prompt 中，而是留给底层虚拟文件系统 (VFS) 注入。
    """

    def __init__(
            self,
            db: AsyncSession,
            agent: Any,  # 数据库 Agent 模型实例
            thread_id: str,
            resume_payload: Optional[Dict[str, Any]] = None,
            enable_tools: bool = False,
            enable_resource_merge: bool = False,
            external_tools: Optional[List[BaseTool]] = None
    ):
        self.db = db
        self.agent = agent
        self.thread_id = thread_id
        self.resume_payload = resume_payload
        self.enable_tools = enable_tools
        self.enable_resource_merge = enable_resource_merge
        self.external_tools = external_tools or []

        self.providers: List[BaseToolProvider] = []
        self.hitl_interrupt_on: Dict[str, bool] = {}

    async def initialize(self) -> Tuple[AgentConfig, str]:
        extended_prompts: List[str] = []
        skills = []

        # 1. 资源挂载与分发 (从 Agent 表读取 resourcePromptList)
        if self.enable_resource_merge and self.agent.resourcePromptList:
            dispatcher = ResourceDispatcher(self.db)
            dispatch_result = await dispatcher.dispatch(self.agent.resourcePromptList)

            for content in dispatch_result.get("system_prompts", []):
                extended_prompts.append(content)
            for content in dispatch_result.get("submessage_templates", []):
                extended_prompts.append(content)

            # 提取 skills 列表，不拼接到 prompt 中
            skills = dispatch_result.get("skills", [])

        if skills:
            file_service = FileService(self.db)
            for skill in skills:
                for file_config in skill.files:
                    try:
                        # 异步读取纯文本内容并赋值
                        file_config.content = await file_service.get_text_content(file_config.file_id)
                    except Exception:
                        # 忽略读取失败的文件，防止阻断
                        file_config.content = ""

        # 2. 外部工具挂载 (MCP & Suggest)
        if self.enable_tools:
            params = {}
            if self.agent and self.agent.modelParameters:
                try:
                    params = json.loads(self.agent.modelParameters) if isinstance(self.agent.modelParameters, str) else self.agent.modelParameters
                except (json.JSONDecodeError, TypeError):
                    pass

            # MCP 服务
            mcp_ids = self.agent.enabledMcpIds or []
            if mcp_ids:
                self.providers.append(MCPToolProvider(self.db, mcp_ids))

                # 提取 HITL 审核配置
                mcp_tools = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                for tool in mcp_tools:
                    if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                        self.hitl_interrupt_on[tool.name] = True

            # Suggest 建议工具
            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

        # 强制追加 DeepAgentBuiltinToolProvider，处理内置文件操作工具的 UI 兼容
        self.providers.append(DeepAgentBuiltinToolProvider())

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
        agent_config = AgentConfig(
            agent_type=AgentTypeEnum.DEEP,  # 强制使用 DEEP 类型
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
