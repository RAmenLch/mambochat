# backend/services/mcp_connection_manager.py

import os
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from backend.models.mcp_model import McpServer
from backend.services import mcp_service
from backend.schemas import enums as schemas_enums
from backend.config.timezone_config import get_configured_now


class McpConnectionError(Exception):
    """MCP 连接或初始化失败时抛出的异常"""

    def __init__(self, server_name: str, error_message: str):
        self.server_name = server_name
        self.error_message = error_message
        super().__init__(f"MCP服务 '{server_name}' 不可用: {error_message}")


def make_httpx_client_factory(proxy_url: Optional[str], *, trust_env: bool):
    """构造 httpx.AsyncClient 工厂，供 MCP HTTP 传输注入（对齐 mambo_agents 实现）。

    保持 MCP 默认行为（follow_redirects=True、30s/300s 超时），
    仅控制 proxy 与 trust_env：trust_env=False 时屏蔽环境变量代理，连接行为完全显式。
    """
    from mcp.shared._httpx_utils import (
        MCP_DEFAULT_SSE_READ_TIMEOUT,
        MCP_DEFAULT_TIMEOUT,
    )

    def _factory(
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[httpx.Timeout] = None,
        auth: Optional[httpx.Auth] = None,
    ) -> httpx.AsyncClient:
        if timeout is None:
            timeout = httpx.Timeout(
                MCP_DEFAULT_TIMEOUT,
                read=MCP_DEFAULT_SSE_READ_TIMEOUT,
            )
        return httpx.AsyncClient(
            proxy=proxy_url,
            trust_env=trust_env,
            follow_redirects=True,
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    return _factory


def _apply_http_proxy(http_config: Dict[str, Any], use_proxy: bool,
                      proxy_enabled: bool, proxy_url: Optional[str]) -> None:
    """为 http 传输配置注入代理行为。

    use_proxy=True 且全局代理开启时显式走 proxy_url；
    其余情况一律直连（trust_env=False），避免环境变量代理的隐式干扰。
    """
    if use_proxy and proxy_enabled and proxy_url:
        http_config["httpx_client_factory"] = make_httpx_client_factory(
            proxy_url, trust_env=False
        )
    else:
        http_config["httpx_client_factory"] = make_httpx_client_factory(
            None, trust_env=False
        )


class McpConnectionManager:
    """
    MCP 连接管理器
    负责初始化 MCP 客户端、验证连接健康状态、记录错误信息到数据库，
    并向调用方提供可用的工具列表。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    async def test_config(config: dict) -> List[BaseTool]:
        """
        使用传入的配置直接测试 MCP 连接，不依赖数据库。
        用于在保存前验证配置是否正确。

        Args:
            config: MultiServerMCPClient 所需的配置字典，格式与 get_tools_and_check_status 中构建的一致。
                    需要包含一个 key 作为 server_name，值为 {"transport", "command"?, "args"?, "env"?, "url"?}。
        """
        client = MultiServerMCPClient(config)
        server_name = list(config.keys())[0]
        tools = await client.get_tools(server_name=server_name)
        return tools

    async def _load_global_proxy(self) -> tuple[bool, Optional[str]]:
        """读取全局代理配置: (proxy_enabled, proxy_url)。"""
        from backend.crud import setting_crud

        proxy_setting = await setting_crud.get_setting(self.db, "proxy_enabled")
        proxy_url_setting = await setting_crud.get_setting(self.db, "proxy_url")
        is_enabled = proxy_setting.value == "True" if proxy_setting else False
        proxy_url = proxy_url_setting.value if proxy_url_setting else None
        return is_enabled, proxy_url

    async def get_tools_and_check_status(self, mcp_ids: List[str]) -> List[BaseTool]:
        """
        加载指定 ID 的 MCP 服务，验证连接并获取工具。
        如果连接失败，会更新数据库状态并抛出异常以阻断生成流程。

        Args:
            mcp_ids: MCP Server ID 列表。
        """
        if not mcp_ids:
            return []

        # 1. 加载配置
        configs = {}
        id_map = {}  # server_id -> config_object

        for mcp_id in mcp_ids:
            config = await mcp_service.load_mcp_config_by_id(self.db, mcp_id)
            if not config or not config.isEnabled:
                continue

            id_map[config.id] = config

            # 构建 MultiServerMCPClient 所需的配置字典
            if config.transportType == schemas_enums.McpTransportType.STDIO:
                # 环境变量优先级: 系统环境 < 静态配置
                current_env = os.environ.copy()

                if config.env:
                    current_env.update(config.env)

                stdio_config = {
                    "transport": "stdio",
                    "command": config.command,
                    "args": config.args,
                    "env": current_env
                }
                if config.cwd:
                    stdio_config["cwd"] = config.cwd
                configs[config.id] = stdio_config
            elif config.transportType in (schemas_enums.McpTransportType.SSE, schemas_enums.McpTransportType.STREAMABLE_HTTP):
                http_config: Dict[str, Any] = {
                    "transport": config.transportType.value,
                    "url": config.url
                }
                if config.headers:
                    http_config["headers"] = config.headers
                if config.timeout is not None:
                    http_config["timeout"] = config.timeout
                if config.sse_read_timeout is not None:
                    http_config["sse_read_timeout"] = config.sse_read_timeout
                proxy_enabled, proxy_url = await self._load_global_proxy()
                _apply_http_proxy(
                    http_config,
                    use_proxy=bool(config.useProxy),
                    proxy_enabled=proxy_enabled,
                    proxy_url=proxy_url,
                )
                configs[config.id] = http_config

        if not configs:
            return []

        # 2. 初始化客户端
        # 注意：MultiServerMCPClient 初始化时暂不建立连接，连接发生在 get_tools 调用时
        client = MultiServerMCPClient(configs)

        all_tools = []
        errors = []

        # 3. 逐个验证连接并获取工具
        # 虽然 client.get_tools() 可以一次性获取所有，但为了精确记录每个服务的状态，
        # 我们按 Server ID 分别获取。
        for server_id, config in id_map.items():
            try:
                # 尝试获取单个服务的工具，这将触发实际的连接建立
                tools = await client.get_tools(server_name=server_id)
                all_tools.extend(tools)

                # 连接成功：更新状态
                await self._update_status(server_id, is_system=config.isSystem, is_healthy=True)

            except Exception as e:
                error_msg = str(e)
                tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))

                # 连接失败：更新状态并记录错误
                await self._update_status(
                    server_id,
                    is_system=config.isSystem,
                    is_healthy=False,
                    error_msg=tb_str
                )

                # 记录简短错误用于抛出
                errors.append(f"[{config.name}] {error_msg}:\n{tb_str}")

        # 4. 如果有任何服务失败，抛出异常以熔断流程
        if errors:
            # 关闭可能已打开的连接（依赖 client 的清理机制，如果有的话）
            # 目前 MultiServerMCPClient 没有显式 close，但在销毁时会处理
            raise McpConnectionError(
                server_name="Multiple" if len(errors) > 1 else list(id_map.keys())[0],
                error_message="; ".join(errors)
            )

        return all_tools

    async def _update_status(
            self,
            server_id: str,
            is_system: bool,
            is_healthy: bool,
            error_msg: Optional[str] = None
    ):
        """
        更新 MCP 服务的状态信息到数据库。
        系统内置服务跳过数据库更新。
        """
        if is_system:
            return

        status_str = "healthy" if is_healthy else "unhealthy"
        now = get_configured_now()

        stmt = (
            update(McpServer)
            .where(McpServer.id == server_id)
            .values(
                last_status=status_str,
                last_test_at=now,
                last_error=error_msg if not is_healthy else None
            )
        )

        try:
            await self.db.execute(stmt)
            await self.db.commit()
        except Exception as e:
            print(f"[McpConnectionManager] Failed to update status for {server_id}: {e}")
            # 状态更新失败不应阻断主流程，仅打印日志
