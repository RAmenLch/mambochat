"""生图配置 → 标准实现的装配。

支持两种后端类型（``ImageGenConfig.backendType``）：

* ``mcp``   —— 绑定一个实现生图标准的 MCP 服务；
* ``model`` —— 绑定系统里已配置的、能出图的 Chat 模型。

运行期（agent 构建）与配置期（生图服务的合规检测）共用这里的装配逻辑，
保证两处使用完全一致的连接参数（proxy / timeout / env）。
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from mambo_agents.middleware.mcp import MCPServerConfig

from backend.models.image_gen_model import ImageGenConfig
from backend.services.generation.tools.mambo_mcp_tool_provider import MamboMCPToolProvider

from .mcp_standard import McpImageGenStandard
from .model_standard import PROTOCOL_CHAT, PROTOCOL_GOOGLE, ChatModelImageGenStandard
from .standard import (
    DEFAULT_RESOLUTION,
    DEFAULT_WAIT_TIMEOUT,
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_NAMES,
    REFERENCE_ARG,
    ImageGenStandard,
    ImageGenToolError,
)

logger = logging.getLogger(__name__)

# 后端类型
BACKEND_MCP = "mcp"
BACKEND_MODEL = "model"

# 参考图能力探测结果缓存：{cache_key: bool}
_REFERENCE_CAPABILITY_CACHE: Dict[str, bool] = {}


class ImageGenConfigError(Exception):
    """生图配置不可用（服务缺失 / 未启用 / 不合规）。"""


def _backend_type(config: ImageGenConfig) -> str:
    return (getattr(config, "backendType", None) or BACKEND_MCP).strip().lower()


def _session_factory():
    from backend.database import AsyncSessionLocal

    return lambda: AsyncSessionLocal()


# ---------------------------------------------------------------------------
# MCP 后端
# ---------------------------------------------------------------------------


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


async def probe_mcp_reference_support(
    server_config: MCPServerConfig,
) -> Tuple[bool, Optional[str]]:
    """检测服务的 ``image_generate`` 是否声明了 ``reference_images``。

    Returns
    -------
    (是否支持, 错误描述)
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {server_config.name: server_config.to_connection()}
    )
    try:
        tools = await client.get_tools(server_name=server_config.name)
    except Exception as exc:  # noqa: BLE001 - 探测失败按不支持处理
        return False, f"{type(exc).__name__}: {exc}"

    tool = next((t for t in tools if t.name == IMAGE_TOOL_GENERATE), None)
    if tool is None:
        return False, f"服务未提供 {IMAGE_TOOL_GENERATE}"
    return REFERENCE_ARG in (getattr(tool, "args", None) or {}), None


async def resolve_reference_support(
    db: AsyncSession, config: ImageGenConfig
) -> bool:
    """配置里钉住了就用配置值，否则探测一次并缓存。"""
    declared = getattr(config, "supportsReferenceImages", None)
    if declared is not None:
        return bool(declared)

    cache_key = f"{config.id}:{config.mcpServerId}"
    if cache_key in _REFERENCE_CAPABILITY_CACHE:
        return _REFERENCE_CAPABILITY_CACHE[cache_key]

    try:
        server_config = await _load_server_config(db, config)
    except ImageGenConfigError as exc:
        logger.warning("参考图能力探测跳过（配置不可用）: %s", exc)
        return False

    supported, error = await probe_mcp_reference_support(server_config)
    if error:
        logger.warning("参考图能力探测失败，按不支持处理: %s", error)
    _REFERENCE_CAPABILITY_CACHE[cache_key] = supported
    return supported


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
        supports_reference_images=await resolve_reference_support(db, config),
    )


# ---------------------------------------------------------------------------
# 系统模型后端
# ---------------------------------------------------------------------------


def model_supports_image_output(meta: Optional[str]) -> bool:
    """模型元配置是否声明可输出图片（``output_modalities`` 含 image）。"""
    if not meta:
        return False
    try:
        data = json.loads(meta) if isinstance(meta, str) else dict(meta)
    except (ValueError, TypeError):
        return False
    modalities = data.get("output_modalities") or []
    return "image" in [str(m).lower() for m in modalities]


async def load_model_backend_config(
    db: AsyncSession, config: ImageGenConfig
) -> Dict[str, Any]:
    """读取绑定的 AIModel / AIProvider，返回构建实现所需的快照。"""
    from backend.crud import provider_crud

    if not config.aiModelId:
        raise ImageGenConfigError(f"生图配置 '{config.name}' 未绑定系统模型")

    model = await provider_crud.get_model(db, config.aiModelId)
    if model is None:
        raise ImageGenConfigError(
            f"生图配置 '{config.name}' 绑定的模型不存在（id={config.aiModelId}）"
        )
    provider = model.provider
    if provider is None:
        raise ImageGenConfigError(
            f"生图配置 '{config.name}' 绑定的模型没有关联服务商"
        )

    return {
        "model_id": model.modelId,
        "model_name": model.name,
        "api_host": provider.apiHost,
        "api_key": provider.apiKey,
        "worker_type": provider.worker_type,
        "use_proxy": bool(provider.use_proxy),
        "declares_image_output": model_supports_image_output(model.meta_config),
        "provider_name": provider.name,
    }


async def build_model_image_standard(
    db: AsyncSession, config: ImageGenConfig
) -> ChatModelImageGenStandard:
    """按配置构建「系统模型」实现；配置不可用时抛 :class:`ImageGenConfigError`。"""
    info = await load_model_backend_config(db, config)

    declared = getattr(config, "supportsReferenceImages", None)
    try:
        return ChatModelImageGenStandard(
            model_id=info["model_id"],
            api_host=info["api_host"],
            api_key=info["api_key"],
            worker_type=info["worker_type"],
            use_proxy=info["use_proxy"],
            timeout=config.timeout,
            session_factory=_session_factory(),
            default_count=config.defaultCount or 1,
            default_sync=bool(config.defaultSync),
            default_resolution=(
                getattr(config, "defaultResolution", "") or DEFAULT_RESOLUTION
            ),
            default_wait_timeout=(
                getattr(config, "defaultWaitTimeout", 0) or DEFAULT_WAIT_TIMEOUT
            ),
            supports_reference_images=True if declared is None else bool(declared),
        )
    except ImageGenToolError as exc:
        raise ImageGenConfigError(str(exc)) from exc


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


async def build_image_standard(
    db: AsyncSession, config: ImageGenConfig
) -> ImageGenStandard:
    """按 ``backendType`` 构建对应实现。"""
    if _backend_type(config) == BACKEND_MODEL:
        return await build_model_image_standard(db, config)
    return await build_mcp_image_standard(db, config)


async def build_image_gen_standard_from_chat_id(
    db: AsyncSession, chat_id: str
) -> Optional[ImageGenStandard]:
    """按会话所属 Agent 的生图配置重建标准实现。

    供 pending file 轮询器这类「独立于生成任务生命周期」的场景使用：同步模式
    由工具自己完成下载，异步模式则需要在 Agent 跑完之后由平台后台把图取回。
    会话未配置生图 / 未启用 / 服务不可用时返回 ``None``（调用方按原逻辑兜底）。
    """
    from backend.crud import chat_crud, agent_crud, image_gen_crud

    try:
        chat = await chat_crud.get_chat(db, chat_id=chat_id)
        if not chat or not chat.agentId:
            return None
        agent = await agent_crud.get_agent(db, chat.agentId)
        if not agent:
            return None

        ig = (agent.agentParameters or {}).get("image_gen") or {}
        if not ig.get("enabled") or not ig.get("configId"):
            return None

        config = await image_gen_crud.get_image_gen_config(db, ig["configId"])
        if not config or not config.isEnabled:
            return None
        return await build_image_standard(db, config)
    except ImageGenConfigError as exc:
        logger.warning("异步生图下载：生图配置不可用: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - 后台轮询不应因配置解析失败中断
        logger.warning("异步生图下载：解析会话生图配置失败: %s", exc)
        return None


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


async def check_reference_support(
    db: AsyncSession, config: ImageGenConfig
) -> Tuple[bool, Optional[str]]:
    """检测接口用：MCP 后端探测 schema，模型后端恒为支持。"""
    if _backend_type(config) == BACKEND_MODEL:
        declared = getattr(config, "supportsReferenceImages", None)
        return (True if declared is None else bool(declared)), None

    try:
        server_config = await _load_server_config(db, config)
    except ImageGenConfigError as exc:
        return False, str(exc)
    return await probe_mcp_reference_support(server_config)


__all__ = [
    "BACKEND_MCP",
    "BACKEND_MODEL",
    "PROTOCOL_CHAT",
    "PROTOCOL_GOOGLE",
    "ImageGenConfigError",
    "build_image_gen_standard_from_chat_id",
    "build_image_standard",
    "build_mcp_image_standard",
    "build_model_image_standard",
    "check_mcp_image_service",
    "check_reference_support",
    "load_model_backend_config",
    "model_supports_image_output",
    "probe_mcp_reference_support",
    "resolve_reference_support",
]
