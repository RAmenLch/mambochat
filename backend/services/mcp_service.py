import sys
import os
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.config.mcp_config import BING_MCP_SERVER_PATH


class McpClientService:
    """
    封装 MCP 客户端逻辑，负责与 MCP 服务器子进程通信。
    """

    def __init__(self, script_path: str = str(BING_MCP_SERVER_PATH)):
        self.script_path = script_path
        self.session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        """
        启动 MCP 服务器子进程并建立会话连接。
        """
        # 配置服务器参数，使用当前 Python 解释器运行目标脚本
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.script_path],
            env=os.environ.copy()  # 继承当前环境以确保依赖可用
        )

        # 使用 AsyncExitStack 管理上下文，保持连接直到显式调用 close
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))

        await self.session.initialize()

    async def get_openai_tools(self) -> List[Dict[str, Any]]:
        """
        获取 MCP 工具列表并转换为 OpenAI API 兼容的格式。
        """
        if not self.session:
            raise RuntimeError("MCP session is not connected.")

        result = await self.session.list_tools()
        openai_tools = []

        for tool in result.tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            })

        return openai_tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        调用指定的 MCP 工具并返回结果文本。
        """
        if not self.session:
            raise RuntimeError("MCP session is not connected.")

        result = await self.session.call_tool(name, arguments)

        # 提取文本内容结果
        content_list = []
        if hasattr(result, 'content') and result.content:
            for item in result.content:
                if item.type == 'text':
                    content_list.append(item.text)
                # 暂不处理 image 或 resource 类型，按需扩展

        return "\n".join(content_list)

    async def close(self):
        """
        关闭会话并清理子进程资源。
        """
        await self._exit_stack.aclose()
        self.session = None
