# backend/services/generation/tools/mcp_tool_provider.py

import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.tools import BaseTool, StructuredTool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.mcp_connection_manager import McpConnectionManager
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus
)
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.models.base_model import generate_uuid

logger = logging.getLogger(__name__)


class MCPToolProvider(BaseToolProvider):
    """
    MCP (Model Context Protocol) 工具提供者。
    负责管理通过 MCP 协议连接的外部工具，并处理其 UI 交互逻辑。
    """

    def __init__(self, db_session: AsyncSession, mcp_ids: List[str]):
        self.db_session = db_session
        self.mcp_ids = mcp_ids
        self.conn_manager = McpConnectionManager(db_session)

        # 缓存已加载的工具名称，用于快速匹配
        self._loaded_tool_names: set[str] = set()

        # 状态映射：tool_call_id -> sub_message_id
        self._tool_sub_msg_map: Dict[str, str] = {}

        # 工具信息缓存：tool_call_id -> McpToolContent
        # 用于在接收到结果时，结合之前的调用信息构建完整的更新 Payload
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        """
        使用 McpConnectionManager 连接并获取工具。
        对每个 MCP 工具进行异常安全包装，防止工具执行时的未处理异常
        (如 ToolException) 冒泡导致整个生成流程崩溃。
        """
        if not self.mcp_ids:
            return []

        # 获取工具并检查状态 (如果服务不可用，此处可能会抛出 McpConnectionError，由上层 Manager 捕获)
        tools = await self.conn_manager.get_tools_and_check_status(self.mcp_ids)

        # 过滤掉数据库中 is_enabled=False 的工具
        from sqlalchemy import select
        from backend.models.mcp_model import McpTool
        result = await self.db_session.execute(
            select(McpTool).filter(
                McpTool.server_id.in_(self.mcp_ids),
                McpTool.is_enabled == False
            )
        )
        disabled_tool_names = {t.name for t in result.scalars().all()}
        if disabled_tool_names:
            tools = [t for t in tools if t.name not in disabled_tool_names]

        # 对每个 MCP 工具进行异常安全包装
        safe_tools = [self._wrap_tool_safe(t) for t in tools]

        # 更新名称缓存
        self._loaded_tool_names = {t.name for t in safe_tools}
        return safe_tools

    @staticmethod
    def _wrap_tool_safe(tool: BaseTool) -> BaseTool:
        """
        用 StructuredTool 重新包装 MCP 工具，在 coroutine 内捕获所有异常
        并返回错误文本，而非让异常冒泡导致整个生成流程崩溃。
        ToolNode 会收到正常结果，LLM 可以看到错误信息并继续推理。
        """
        tool_name = tool.name
        original_coroutine = tool.coroutine

        async def safe_coroutine(*args, **kwargs):
            try:
                return await original_coroutine(*args, **kwargs)
            except Exception as e:
                logger.warning(f"MCP tool '{tool_name}' execution error: {e}")
                return f"工具执行失败: {e}"

        return StructuredTool(
            name=tool_name,
            description=tool.description,
            args_schema=tool.args_schema,
            coroutine=safe_coroutine,
        )

    def get_system_prompt_injection(self) -> Optional[str]:
        # MCP 工具通常不需要额外的全局 System Prompt 注入，
        # 因为 LangChain/LLM 会自动处理工具定义的 Schema。
        return None

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in self._loaded_tool_names

    async def create_call_instruction(
            self,
            tool_call_id: str,
            name: str,
            arguments: Dict[str, Any],
            tool_def: Optional[BaseTool] = None,
            run_uuid: Optional[str] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        # 1. 提取工具定义中的 JSON Schema
        input_schema = tool_def.args if tool_def else None

        # 2. 构建包含 Schema 的 McpToolContent 对象
        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema,  # 注入 Schema
            run_uuid=run_uuid,
        )

        # 3. 缓存状态，建立 ID 映射
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
            config=SubMessageConfig(is_minimal=True)
        )

    async def create_result_instruction(
            self,
            tool_call_id: str,
            result_text: str,
            is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:
        # 检查该 tool_call_id 是否属于本 Provider 管理
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
