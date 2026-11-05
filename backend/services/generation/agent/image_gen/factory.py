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
from backend.services.generation.image_executors import (
    ExecutorError,
    ImageApiExecutor,
    resolve_executor,
)
from backend.services.generation.tools.mambo_mcp_tool_provider import MamboMCPToolProvider

from .api_standard import ImageApiImageGenStandard
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
BACKEND_IMAGE_API = "image_api"

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


def _meta_dict(meta: Optional[str]) -> Dict[str, Any]:
    """把 ``AIModel.meta_config``（TEXT）解析成字典，失败返回空字典。"""
    if not meta:
        return {}
    try:
        data = json.loads(meta) if isinstance(meta, str) else dict(meta)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def model_supports_image_output(meta: Optional[str]) -> bool:
    """模型元配置是否声明可输出图片（``output_modalities`` 含 image）。"""
    modalities = _meta_dict(meta).get("output_modalities") or []
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
    meta = _meta_dict(model.meta_config)
    provider = model.provider
    if provider is None:
        raise ImageGenConfigError(
            f"生图配置 '{config.name}' 绑定的模型没有关联服务商"
        )

    return {
        "model_id": model.modelId,
        "model_name": model.name,
        "model_type": (model.model_type or "").strip().lower(),
        "api_host": provider.apiHost,
        "api_key": provider.apiKey,
        "worker_type": provider.worker_type,
        "use_proxy": bool(provider.use_proxy),
        "declares_image_output": model_supports_image_output(model.meta_config),
        "image_options": meta.get("image_options") or {},
        "image_capabilities": meta.get("image_capabilities") or {},
        "provider_name": provider.name,
    }


def resolve_model_executor(info: Dict[str, Any]) -> ImageApiExecutor:
    """按服务商信息解析该生图模型应使用的执行器。

    服务商的 ``worker_type`` 是生图执行器时直接命中；否则按 ``api_host`` 推断
    （OpenRouter 网关 → OpenRouter Images，其余 OpenAI 兼容 → OpenAI Images）。
    """
    try:
        return resolve_executor(info.get("worker_type"), info.get("api_host"))
    except ExecutorError as exc:
        raise ImageGenConfigError(str(exc)) from exc


async def build_model_image_standard(
    db: AsyncSession, config: ImageGenConfig
) -> ChatModelImageGenStandard:
    """按配置构建「系统模型」实现；配置不可用时抛 :class:`ImageGenConfigError`。"""
    info = await load_model_backend_config(db, config)
    if info["model_type"] == "image":
        raise ImageGenConfigError(
            f"模型 {info['model_name']} 是生图模型（model_type=image），"
            "请把生图配置的后端类型改为「生图模型」"
        )

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


def _min_input_references(capabilities: Dict[str, Any]) -> int:
    """模型声明的参考图下限（``input_references.min``），未声明视为 0。"""
    declared = (capabilities or {}).get("supported_parameters")
    if not isinstance(declared, dict):
        return 0
    descriptor = declared.get("input_references")
    if not isinstance(descriptor, dict):
        return 0
    try:
        return int(descriptor.get("min") or 0)
    except (TypeError, ValueError):
        return 0


async def build_image_api_standard(
    db: AsyncSession, config: ImageGenConfig
) -> ImageApiImageGenStandard:
    """按配置构建「纯生图接口」实现（执行器由服务商决定）。"""
    info = await load_model_backend_config(db, config)
    if info["model_type"] != "image":
        raise ImageGenConfigError(
            f"模型 {info['model_name']} 不是生图模型（model_type={info['model_type'] or 'chat'}），"
            "请把它设为 image，或把生图配置的后端类型改为「系统模型」"
        )

    executor = resolve_model_executor(info)
    declared = getattr(config, "supportsReferenceImages", None)

    # 模型要求必须带参考图时，参考图参数不能被配置钉死为「不支持」
    reference_required = _min_input_references(info["image_capabilities"]) >= 1
    if reference_required:
        if declared is False:
            logger.warning(
                "生图配置 '%s' 的模型 %s 要求至少 %s 张参考图，"
                "但配置把参考图能力钉成了「不支持」，已按支持处理",
                config.name,
                info["model_id"],
                _min_input_references(info["image_capabilities"]),
            )
        supports_reference = True
    else:
        supports_reference = (
            executor.supports_reference_images if declared is None else bool(declared)
        )

    try:
        return ImageApiImageGenStandard(
            executor=executor,
            model_id=info["model_id"],
            api_host=info["api_host"],
            api_key=info["api_key"],
            use_proxy=info["use_proxy"],
            timeout=config.timeout,
            session_factory=_session_factory(),
            image_options=info["image_options"],
            capabilities=info["image_capabilities"],
            default_count=config.defaultCount or 1,
            default_sync=bool(config.defaultSync),
            default_resolution=(
                getattr(config, "defaultResolution", "") or DEFAULT_RESOLUTION
            ),
            default_wait_timeout=(
                getattr(config, "defaultWaitTimeout", 0) or DEFAULT_WAIT_TIMEOUT
            ),
            supports_reference_images=supports_reference,
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
    backend = _backend_type(config)
    if backend == BACKEND_IMAGE_API:
        return await build_image_api_standard(db, config)
    if backend == BACKEND_MODEL:
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


async def _image_api_client(db: AsyncSession, use_proxy: bool):
    from backend.services.provider_service import _get_http_client_with_proxy

    return await _get_http_client_with_proxy(
        db, use_proxy_flag=use_proxy, timeout=30
    )


async def _probe_openrouter_images(
    db: AsyncSession, info: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """拉 ``/images/models`` 并挑出目标模型的能力描述符。"""
    import httpx

    url = f"{info['api_host'].rstrip('/')}/images/models"
    headers = {"Authorization": f"Bearer {info['api_key']}"}
    try:
        async with await _image_api_client(db, info["use_proxy"]) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return None, f"HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except (ValueError, TypeError) as exc:
        return None, f"响应不是合法 JSON: {exc}"

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None, "响应缺少 data 列表"
    for item in items:
        if isinstance(item, dict) and str(item.get("id")) == str(info["model_id"]):
            return {
                "architecture": item.get("architecture"),
                "supported_parameters": item.get("supported_parameters"),
                "supports_streaming": item.get("supports_streaming"),
            }, None
    return None, f"图片模型列表中没有 {info['model_id']}"


async def _probe_openai_models(
    db: AsyncSession, info: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``/models`` 里确认模型存在（OpenAI 不返回生图能力描述）。"""
    import httpx

    url = f"{info['api_host'].rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {info['api_key']}"}
    try:
        async with await _image_api_client(db, info["use_proxy"]) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return None, f"HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except (ValueError, TypeError) as exc:
        return None, f"响应不是合法 JSON: {exc}"

    items = payload.get("data") if isinstance(payload, dict) else None
    ids = [
        str(item.get("id"))
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict)
    ]
    if str(info["model_id"]) in ids:
        return {"architecture": None, "supported_parameters": None}, None
    return None, f"模型列表中没有 {info['model_id']}"


async def probe_image_endpoint(
    db: AsyncSession, config: ImageGenConfig
) -> Dict[str, Any]:
    """检测纯生图后端：只做 GET 探测（校验 Key / 模型存在 / 拉能力），不生成图片。"""
    info = await load_model_backend_config(db, config)
    if info["model_type"] != "image":
        raise ImageGenConfigError(
            f"模型 {info['model_name']} 不是生图模型（model_type="
            f"{info['model_type'] or 'chat'}），请先把模型类型设为 image"
        )

    executor = resolve_model_executor(info)
    detail: Dict[str, Any] = {
        "executor": executor.key,
        "label": executor.label,
        "paths": list(executor.paths),
        "options": sorted(executor.whitelist()),
        "model_id": info["model_id"],
        "provider_name": info["provider_name"],
        "supports_reference_images": executor.supports_reference_images,
        "capabilities": dict(info["image_capabilities"] or {}),
    }

    if executor.key == "openrouter_images":
        remote, error = await _probe_openrouter_images(db, info)
    else:
        remote, error = await _probe_openai_models(db, info)

    if remote:
        merged = dict(detail["capabilities"] or {})
        for key, value in remote.items():
            if value is not None:
                merged[key] = value
        detail["capabilities"] = merged
    if error:
        detail["error"] = error
    detail["declared"] = remote is not None
    return detail


async def check_reference_support(
    db: AsyncSession, config: ImageGenConfig
) -> Tuple[bool, Optional[str]]:
    """检测接口用：MCP 后端探测 schema，模型 / 纯生图后端按执行器能力。"""
    backend = _backend_type(config)
    if backend in (BACKEND_MODEL, BACKEND_IMAGE_API):
        declared = getattr(config, "supportsReferenceImages", None)
        if declared is not None:
            return bool(declared), None
        if backend == BACKEND_IMAGE_API:
            try:
                info = await load_model_backend_config(db, config)
                return resolve_model_executor(info).supports_reference_images, None
            except ImageGenConfigError as exc:
                return False, str(exc)
        return True, None

    try:
        server_config = await _load_server_config(db, config)
    except ImageGenConfigError as exc:
        return False, str(exc)
    return await probe_mcp_reference_support(server_config)


__all__ = [
    "BACKEND_IMAGE_API",
    "BACKEND_MCP",
    "BACKEND_MODEL",
    "PROTOCOL_CHAT",
    "PROTOCOL_GOOGLE",
    "ImageGenConfigError",
    "build_image_api_standard",
    "build_image_gen_standard_from_chat_id",
    "build_image_standard",
    "build_mcp_image_standard",
    "build_model_image_standard",
    "check_mcp_image_service",
    "check_reference_support",
    "load_model_backend_config",
    "model_supports_image_output",
    "probe_image_endpoint",
    "probe_mcp_reference_support",
    "resolve_model_executor",
    "resolve_reference_support",
]
