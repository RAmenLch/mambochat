# backend/services/generation/builders/initializers/deep_agent_initializer.py

import json
import asyncio
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.schemas.enums import ToolReviewMode, AgentTypeEnum
from backend.crud import mcp_crud, agent_crud

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
    解析数据库配置，提取主代理与子代理 (Subagents) 的技能库路径与工具，生成标准化的 AgentConfig。
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

        # 实例化文件服务与资源分发器
        file_service = FileService(self.db)
        dispatcher = ResourceDispatcher(self.db)

        # ==========================================
        # 1. 主代理 (Main Agent) 资源与工具装配
        # ==========================================

        # 1.1 资源挂载与分发 (Skills & Prompts)
        if self.enable_resource_merge and self.agent.resourcePromptList:
            dispatch_result = await dispatcher.dispatch(self.agent.resourcePromptList)

            for content in dispatch_result.get("system_prompts", []):
                extended_prompts.append(content)
            for content in dispatch_result.get("submessage_templates", []):
                extended_prompts.append(content)

            # 提取 skills 列表，不拼接到 prompt 中
            skills = dispatch_result.get("skills", [])

        if skills:
            for skill in skills:
                for file_config in skill.files:
                    try:
                        # 异步读取纯文本内容并赋值，供 VFS 初始化使用
                        file_config.content = await file_service.get_text_content(file_config.file_id)
                    except Exception:
                        file_config.content = ""

        # 1.2 外部工具挂载 (MCP & Suggest)
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
                main_mcp_provider = MCPToolProvider(self.db, mcp_ids)
                self.providers.append(main_mcp_provider)

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
        builtin_provider = DeepAgentBuiltinToolProvider()
        self.providers.append(builtin_provider)

        # 1.3 收集主代理所有工具实例
        all_tools: List[BaseTool] = list(self.external_tools)
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)


        # ==========================================
        # 2. 子代理 (Subagents) 资源与工具装配
        # ==========================================
        subagents_config: List[Dict[str, Any]] = []

        if self.agent.subAgents:
            # 并发获取所有子代理的数据库记录
            sub_agents_db = await asyncio.gather(
                *[agent_crud.get_agent(self.db, sid) for sid in self.agent.subAgents]
            )

            for sub in sub_agents_db:
                if not sub:
                    continue

                sub_tools = []
                sub_skills_paths = []
                sub_interrupt_on = {}

                # 2.1 子代理独立 Skills 解析 (Context Quarantine)
                if sub.resourcePromptList:
                    sub_dispatch = await dispatcher.dispatch(sub.resourcePromptList)
                    sub_skills = sub_dispatch.get("skills", [])

                    if sub_skills:
                        for skill in sub_skills:
                            for file_config in skill.files:
                                try:
                                    file_config.content = await file_service.get_text_content(file_config.file_id)
                                except Exception:
                                    file_config.content = ""

                            # 记录子代理的技能路径
                            sub_skills_paths.append(f"/skills/{skill.name}")

                            # 【关键】将子代理的 SkillConfig 合并到全局 skills 中，
                            # 以便 chat_worker.py 统一将文件内容注入到虚拟文件系统 (VFS) 中
                            skills.append(skill)

                # 2.2 子代理独立 Tools 解析
                if sub.enabledMcpIds:
                    sub_mcp_provider = MCPToolProvider(self.db, sub.enabledMcpIds)
                    sub_tools.extend(await sub_mcp_provider.get_tools())

                    # 【关键】将子代理的 Provider 也加入全局 providers，确保前端能正确渲染其 UI
                    self.providers.append(sub_mcp_provider)

                    # 提取子代理独立的 HITL 拦截配置
                    sub_mcp_tools_db = await mcp_crud.get_tools_by_server_ids(self.db, sub.enabledMcpIds)
                    for t in sub_mcp_tools_db:
                        if t.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                            sub_interrupt_on[t.name] = True

                # 强制为子代理挂载内置文件工具
                sub_tools.extend(await builtin_provider.get_tools())

                # 2.3 组装符合 deepagents 库规范的子代理配置字典
                sub_dict = {
                    "name": sub.name,
                    "description": sub.description or f"Subagent {sub.name} for specific tasks.",
                    "system_prompt": sub.systemPrompt or "You are a helpful sub-assistant. Return ONLY a concise summary of your findings.",
                    "tools": sub_tools,
                }

                if sub_skills_paths:
                    sub_dict["skills"] = sub_skills_paths
                if sub_interrupt_on:
                    sub_dict["interrupt_on"] = sub_interrupt_on

                subagents_config.append(sub_dict)


        # ==========================================
        # 3. 构建最终 AgentConfig
        # ==========================================
        agent_config = AgentConfig(
            agent_type=AgentTypeEnum.DEEP,  # 强制使用 DEEP 类型
            tools=all_tools if all_tools else None,
            skills=skills if skills else None,
            subagents=subagents_config if subagents_config else None, # 注入子代理配置
            hitl_interrupt_on=self.hitl_interrupt_on,
            thread_id=self.thread_id,
            resume_payload=self.resume_payload
        )

        # 合并附加的 System Prompt
        additional_system_prompt = "\n\n".join(extended_prompts) if extended_prompts else ""

        return agent_config, additional_system_prompt

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers

