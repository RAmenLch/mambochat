# backend/services/generation/graph_builders/deep_agent_builder.py

from typing import List
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent

from backend.checkpointer import get_checkpointer
from backend.services.generation.core.llm_io import AgentConfig
from backend.services.generation.graph_builders.base_builder import BaseGraphBuilder


class DeepAgentGraphBuilder(BaseGraphBuilder):
    """
    针对 DeepAgent 架构的图构建器。
    桥接系统配置与 deepagents 核心库，完成 LangGraph 状态图的编译。
    """

    def build(self, model: BaseChatModel, agent_config: AgentConfig) -> CompiledStateGraph:
        # 1. 提取工具列表
        tools = [t for t in agent_config.tools] if agent_config.tools else []

        # 2. 提取技能库根目录名称，构造为 POSIX 路径列表
        skill_paths: List[str] = []
        if agent_config.skills:
            for skill in agent_config.skills:
                # 构造为 POSIX 路径，匹配 VFS 注入时的路径前缀 (如 /skills/SKILL_A)
                # 确保与 chat_worker.py 注入时的虚拟路径保持一致
                skill_paths.append(f"/skills/{skill.name}")

        # 3. 获取全局异步 SQLite Checkpointer
        active_checkpointer = get_checkpointer()

        # 4. 调用 deepagents 核心库编译图
        return create_deep_agent(
            model=model,
            tools=tools,
            skills=skill_paths if skill_paths else None,
            subagents=agent_config.subagents,
            checkpointer=active_checkpointer,
            interrupt_on=agent_config.hitl_interrupt_on
        )

