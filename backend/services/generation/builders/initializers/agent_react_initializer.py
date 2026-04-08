# backend/services/generation/builders/initializers/agent_react_initializer.py

from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool

from backend.schemas.enums import ToolReviewMode, AgentTypeEnum
from backend.models.agent_model import Agent
from backend.crud import mcp_crud

from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.builders.initializers.base_initializer import AbstractAgentInitializer
from backend.services.generation.builders.resource_dispatcher import ResourceDispatcher

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.mcp_tool_provider import MCPToolProvider
from backend.services.generation.tools.suggest_tool_provider import SuggestToolProvider
from backend.services.generation.tools.kb_tool_provider import KBToolProvider


class AgentBasedReActInitializer(AbstractAgentInitializer):
    def __init__(
            self,
            db: AsyncSession,
            agent: Agent,
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
        knowledge_bases = []
        skills = []

        if self.enable_resource_merge and self.agent.resourcePromptList:
            dispatcher = ResourceDispatcher(self.db)
            dispatch_result = await dispatcher.dispatch(self.agent.resourcePromptList)

            extended_prompts.extend(dispatch_result.get("system_prompts", []))
            extended_prompts.extend(dispatch_result.get("submessage_templates", []))
            knowledge_bases = dispatch_result.get("knowledge_bases", [])
            skills = dispatch_result.get("skills", [])

        if knowledge_bases:
            self.providers.append(KBToolProvider(self.db, knowledge_bases))

        if self.enable_tools:
            params = self.agent.parsed_model_parameters

            mcp_ids = self.agent.enabledMcpIds or []
            if mcp_ids:
                self.providers.append(MCPToolProvider(self.db, mcp_ids))

                mcp_tools = await mcp_crud.get_tools_by_server_ids(self.db, mcp_ids)
                for tool in mcp_tools:
                    if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value:
                        self.hitl_interrupt_on[tool.name] = True

            enable_suggest = params.get("enable_suggest", False)
            if enable_suggest:
                self.providers.append(SuggestToolProvider(enable_suggest=True))

        all_tools: List[BaseTool] = list(self.external_tools)
        for provider in self.providers:
            tools = await provider.get_tools()
            if tools:
                all_tools.extend(tools)

            injection = provider.get_system_prompt_injection()
            if injection:
                extended_prompts.append(injection)

        base_prompt = self.agent.systemPrompt or ""
        additional_system_prompt = "\n\n".join(extended_prompts) if extended_prompts else ""
        final_system_prompt = f"{base_prompt}\n\n{additional_system_prompt}".strip() if additional_system_prompt else base_prompt

        agent_config = AgentConfig(
            name=self.agent.name,
            description=self.agent.description or "",
            system_prompt=final_system_prompt,
            agent_type=AgentTypeEnum(self.agent.AgentType),
            tools=all_tools if all_tools else None,
            skills=skills if skills else None,
            hitl_interrupt_on=self.hitl_interrupt_on,
            resume_payload=self.resume_payload
        )

        return agent_config, additional_system_prompt

    def get_providers(self) -> List[BaseToolProvider]:
        return self.providers
