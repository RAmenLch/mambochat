"""生图配置 → 标准实现的装配。

运行期（agent 构建）与配置期（生图服务的合规检测）共用这里的装配逻辑，
保证两处使用完全一致的 MCP 连接参数（proxy / timeout / env）。
"""

import logging
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from mambo_agents.middleware.mcp import MCPServerConfig

from backend.models.image_gen_model import ImageGenConfig
from backend.services.generation.tools.mambo_mcp_tool_provider import MamboMCPToolProvider

from .mcp_standard import McpImageGenStandard
from .standard import (
    DEFAULT_RESOLUTION,
    DEFAULT_WAIT_TIMEOUT,
    IMAGE_TOOL_NAMES,
)

logger = logging.getLogger(__name__)


class ImageGenConfigError(Exception):
    """生图配置不可用（服务缺失 / 未启用 / 不合规）。"""


async def _load_server_config(
    db: AsyncSession, config: ImageGenConfig
) -> MCPServerConfig:
    if not config.mcpServerId:
        raise ImageGenConfigError(f"生图配置 '{config.name}' 未绑定 MCP 服务")

    provider = MamboMCPToolProvider(db, [config.mcpServerId])
    loaded = await provider.load_configs()
    if not loaded:
        raise ImageGenConfigError(
            f"生图配置 '{config.name}' 绑定的 MCP 服务不存在或未启用"
        )

    server_name = provider.id_to_name.get(config.mcpServerId)
    server_config = next(
        (c for c in provider.mcp_server_configs if c.name == server_name), None
    )
    if server_config is None:
        raise ImageGenConfigError(
            f"生图配置 '{config.name}' 绑定的 MCP 服务配置解析失败"
        )

    if config.timeout is not None:
        server_config = server_config.model_copy(update={"timeout": float(config.timeout)})
    return server_config


async def build_mcp_image_standard(
    db: AsyncSession, config: ImageGenConfig
) -> McpImageGenStandard:
    """按配置构建 MCP 实现；配置不可用时抛 :class:`ImageGenConfigError`。"""
    server_config = await _load_server_config(db, config)
    return McpImageGenStandard(
        server_config,
        default_count=config.defaultCount or 1,
        default_sync=bool(config.defaultSync),
        default_resolution=getattr(config, "defaultResolution", "") or DEFAULT_RESOLUTION,
        default_wait_timeout=getattr(config, "defaultWaitTimeout", 0) or DEFAULT_WAIT_TIMEOUT,
    )


async def check_mcp_image_service(
    db: AsyncSession, config: ImageGenConfig
) -> Tuple[List[str], List[str], Optional[str]]:
    """检测绑定的 MCP 服务是否提供三个标准工具。

    Returns
    -------
    (found_tools, missing_tools, error)
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    try:
        server_config = await _load_server_config(db, config)
    except ImageGenConfigError as exc:
        return [], list(IMAGE_TOOL_NAMES), str(exc)

    client = MultiServerMCPClient(
        {server_config.name: server_config.to_connection()}
    )
    try:
        tools = await client.get_tools(server_name=server_config.name)
    except Exception as exc:  # noqa: BLE001 - 检测接口需要返回原始错误
        return [], list(IMAGE_TOOL_NAMES), f"{type(exc).__name__}: {exc}"

    found = sorted(t.name for t in tools)
    missing = [name for name in IMAGE_TOOL_NAMES if name not in set(found)]
    return found, missing, None


__all__ = [
    "ImageGenConfigError",
    "build_mcp_image_standard",
    "check_mcp_image_service",
]
