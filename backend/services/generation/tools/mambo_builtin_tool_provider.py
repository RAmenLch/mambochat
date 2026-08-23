# backend/services/generation/tools/mambo_builtin_tool_provider.py

import json
from typing import List, Optional, Dict, Any, AsyncGenerator

from langchain_core.tools import BaseTool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
)
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.models.base_model import generate_uuid


class MamboAgentBuiltinToolProvider(BaseToolProvider):
    """
    Mambo Agent 内置工具提供者 (UI 兼容层)。

    拦截 mambo_agents 底层隐式注入的内置系统工具调用（来自 BackendToolsMiddleware
    和 SubAgentMiddleware 等），并将其转换为前端可渲染的 UI 消息指令。
    复用现有的 MCP_TOOL 子消息类型，使前端能够无缝展示文件操作、终端执行等进度。

    **后端级工具自动注册**：
    ``register_tool(name)`` 方法允许后续动态注册 backend 暴露的工具名称（如
    ``ls_version``），避免每次新增 backend 工具都要手动更新 ``BUILTIN_TOOLS``。
    """

    # 中间件注入的固定内置工具（与 backend 无关）
    # - core six: ls, read, write, edit, glob, grep (BackendToolsMiddleware)
    # - workspace: copy (HybridWorkspaceBackend 跨后端复制)
    # - backend extras: tree, delete, execute, sandbox_run 等 (由 backend.tools 决定)
    # - subagent: task (SubAgentMiddleware)
    # - async subagent: async_task, async_status (AsyncSubAgentMiddleware)
    # - planning: write_plans (MamboPlanMiddleware)
    # - goal loop: get_goal (GoalLoopMiddleware，可带 tool_prefix；由 matches_tool_name 兼容)
    # 注：backend 专属工具（如 ls_version）通过 register_tool() 动态注入，不在此硬编码
    BUILTIN_TOOLS = frozenset({
        "ls",
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "copy",
        "tree",
        "delete",
        "execute",
        "task",
        "async_task",
        "async_status",
        "write_plans",
        "show",
    })

    def __init__(self, extra_tool_names: frozenset[str] | None = None):
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}
        self._extra_tool_names: set[str] = set(extra_tool_names) if extra_tool_names else set()

    async def get_tools(self) -> List[BaseTool]:
        return []

    def get_system_prompt_injection(self) -> Optional[str]:
        return None

    # GoalLoopMiddleware 在 LLM 模式下注册的三个工具（均可带 tool_prefix，如 "xxx_get_goal"），
    # 需像 write_plans 等中间件工具一样落库为 MCP_TOOL，保证 DB 与 state 对齐。
    _GOAL_LOOP_TOOLS = frozenset({"get_goal", "create_goal", "update_goal"})

    def matches_tool_name(self, tool_name: str) -> bool:
        if tool_name in self._GOAL_LOOP_TOOLS or tool_name.endswith(tuple(self._GOAL_LOOP_TOOLS)):
            return True
        return tool_name in self.BUILTIN_TOOLS or tool_name in self._extra_tool_names

    def register_tool(self, name: str) -> None:
        """动态注册一个后端级工具的名称，使其可被 UI 追踪。"""
        self._extra_tool_names.add(name)

    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None,
        run_uuid: Optional[str] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:

        input_schema = tool_def.args if tool_def else None

        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema,
            run_uuid=run_uuid,
        )

        self._tool_info_cache[tool_call_id] = tool_content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        config = SubMessageConfig(is_minimal=True)
        # GoalLoopMiddleware 注入的 get_goal 调用 id 恒以 "goal-loop-" 开头
        # （对应 mambo_agents.middleware.goal_loop._INJECT_PREFIX），与 LLM 自主
        # 调用的 get_goal（随机 id）区分。该 flag 供前端渲染"轮次分隔线"，
        # 轮次数不在 config 中携带，由前端从 get_goal 的 result 文本解析。
        if name.endswith("get_goal") and tool_call_id.startswith("goal-loop-"):
            config.is_goal_loop_round = True

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=tool_content.to_json_string(),
            config=config,
        )

    async def create_result_instruction(
        self,
        tool_call_id: str,
        result_text: str,
        is_error: bool,
    ) -> AsyncGenerator[BaseInstruction, None]:

        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        # --- show 工具特殊处理：额外创建 FILE 子消息 ---
        if cached_content and cached_content.name == "show" and not is_error:
            try:
                data = json.loads(result_text)

                if data.get("status") == "pending":
                    yield CreateSubMessage(
                        sub_message_id=generate_uuid(),
                        type=schemas_enums.SubMessageType.FILE.value,
                        sortOrder=2,
                        status=schemas_enums.MessageStatus.WAITING,
                        initial_content="",
                        config=SubMessageConfig(
                            context_participation_length=0,
                            pending_file_path=data["path"],
                            pending_file_timeout=data.get("timeout", 300),
                            show_tool_mode=data.get("mode", "Normal"),
                        ),
                    )
                else:
                    file_id = data.get("file_id")
                    if file_id:
                        yield CreateSubMessage(
                            sub_message_id=generate_uuid(),
                            type=schemas_enums.SubMessageType.FILE.value,
                            sortOrder=2,
                            status=schemas_enums.MessageStatus.COMPLETED,
                            initial_content=file_id,
                            config=SubMessageConfig(
                                context_participation_length=0,
                                show_tool_mode=data.get("mode", "Normal"),
                            ),
                        )
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # --- 通用 MCP_TOOL 结果更新 ---
        if sub_id and cached_content:
            cached_content.result = result_text
            cached_content.is_error = is_error

            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string(),
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED,
            )

    def restore_state(
        self, tool_call_id: str, sub_message_id: str, tool_content: Any
    ) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
