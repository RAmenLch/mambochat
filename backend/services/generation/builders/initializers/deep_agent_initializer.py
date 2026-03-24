# backend/services/generation/builders/initializers/deep_agent_initializer.py

import json
import asyncio
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.schemas.enums import ToolReviewMode, AgentTypeEnum
from backend.crud import mcp_crud, agent_crud

from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.builders.initializers.base_initializer import AbstractAgentInitializer
from backend.services.generation.builders.resource_dispatcher import ResourceDispatcher

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mcp_tool_provider import MCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider
from backend.services.generation.tools.deep_builtin_tool_provider import DeepAgentBuiltinToolProvider
from backend.services.file_service import FileService


class DeepAgentInitializer(AbstractAgentInitializer):
    def __init__(
            self,
            db: AsyncSession,
            agent: Any,
            resume_payload: Optional[Dict[str, Any]] = None,
            enable_tools: bool = False,
            enable_resource_merge: bool = False,
            external_tools: Optional[List[BaseTool]] = None
    ):
        self.db = db
        self.agent = agent
        self.resume_payload = resume_payload
        self.enable_tools = enable_tools
        self.enable_resource_merge = enable_resource_merge
        self.external_tools = external_tools or []

        self.providers: List[BaseToolProvider] = []
        self.hitl_interrupt_on: Dict[str, bool] = {}

    async def initialize(self) -> Tuple[AgentConfig, str]:
        extended_prompts: List[str] = []
        skills = []

        file_service = FileService(self.db)
        dispatcher = ResourceDispatcher(self.db)

        if self.enable_resource_merge and self.agent.resourcePromptList:
            dispatch_result = await dispatcher.dispatch(self.agent.resourcePromptList)

            extended_prompts.extend(dispatch_result.get("system_prompts", []))
            extended_prompts.extend(dispatch_result.get("submessage_templates", []))
            skills = dispatch_result.get("skills", [])

        if skills:
            for skill in skills:
                for file_config in skill.files:
                    try:
                        file_config.content = await file_service.get_text_content(file_config.file_id)
                    except Exception:
                        file_config.content = ""

        if self.enable_tools:
            params = {}
            if self.agent and self.agent.modelParameters:
                try:
                    params = json.loads(self.agent.modelParameters) if isinstance(self.agent.modelParameters, str) else self.agent.modelParameters
                except (json.JSONDecodeError, TypeError):
                    pass

            mcp_ids = self.agent.enabledMcpIds or []
            if mcp_ids:
                main_mcp_provider = MCPToolProvider(self.db, mcp_ids)
                self.providers.append(main_mcp_provider)

                mcp_tools = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                for tool in mcp_tools:
                    if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                        self.hitl_interrupt_on[tool.name] = True

            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

        builtin_provider = DeepAgentBuiltinToolProvider()
        self.providers.append(builtin_provider)

        all_tools: List[BaseTool] = list(self.external_tools)
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)

        sub_configs: List[AgentConfig] = []

        if self.agent.subAgents:
            sub_agents_db = await asyncio.gather(
                *[agent_crud.get_agent(self.db, sid) for sid in self.agent.subAgents]
            )

            from backend.services.generation.builders.initializers.agent_react_initializer import AgentBasedReActInitializer

            for sub in sub_agents_db:
                if not sub:
                    continue

                if sub.AgentType == AgentTypeEnum.DEEP.value or sub.AgentType == AgentTypeEnum.DEEP:
                    sub_init = DeepAgentInitializer(
                        db=self.db,
                        agent=sub,
                        resume_payload=self.resume_payload,
                        enable_tools=self.enable_tools,
                        enable_resource_merge=self.enable_resource_merge,
                        external_tools=self.external_tools
                    )
                else:
                    sub_init = AgentBasedReActInitializer(
                        db=self.db,
                        agent=sub,
                        resume_payload=self.resume_payload,
                        enable_tools=self.enable_tools,
                        enable_resource_merge=self.enable_resource_merge,
                        external_tools=self.external_tools
                    )

                sub_config, _ = await sub_init.initialize()
                sub_configs.append(sub_config)
                self.providers.extend(sub_init.get_providers())

        base_prompt = self.agent.systemPrompt or ""
        additional_system_prompt = "\n\n".join(extended_prompts) if extended_prompts else ""
        final_system_prompt = f"{base_prompt}\n\n{additional_system_prompt}".strip() if additional_system_prompt else base_prompt

        agent_config = AgentConfig(
            name=self.agent.name,
            description=self.agent.description or "",
            system_prompt=final_system_prompt,
            agent_type=AgentTypeEnum.DEEP,
            tools=all_tools if all_tools else None,
            skills=skills if skills else None,
            sub_configs=sub_configs if sub_configs else None,
            hitl_interrupt_on=self.hitl_interrupt_on,
            resume_payload=self.resume_payload
        )

        return agent_config, additional_system_prompt

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers
