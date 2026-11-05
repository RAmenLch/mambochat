# backend/routers/image_gen_management.py

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import image_gen_crud
from backend.database import get_db
from backend.schemas.image_gen import (
    ImageGenConfigCreate,
    ImageGenConfigResponse,
    ImageGenConfigUpdate,
    ImageGenToolCheckResult,
)

router = APIRouter()


async def _validate_backend_binding(db: AsyncSession, current, payload) -> None:
    """更新时按「合并后的最终状态」校验后端绑定是否完整。"""
    backend_type = (
        payload.backendType
        if payload.backendType is not None
        else (current.backendType or "mcp")
    ).strip().lower()

    mcp_server_id = (
        payload.mcpServerId
        if payload.mcpServerId is not None
        else current.mcpServerId
    )
    ai_model_id = (
        payload.aiModelId if payload.aiModelId is not None else current.aiModelId
    )

    if backend_type in ("model", "image_api"):
        if not (ai_model_id or "").strip():
            raise HTTPException(
                status_code=400, detail="后端类型为「系统模型」时必须绑定一个模型"
            )
        from backend.crud import provider_crud

        model = await provider_crud.get_model(db, ai_model_id)
        if model is None:
            raise HTTPException(status_code=400, detail="绑定的模型不存在")

        model_type = (model.model_type or "").strip().lower()
        if backend_type == "image_api":
            if model_type != "image":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "后端类型为「生图模型」时只能绑定生图模型"
                        f"（当前模型类型为 {model_type or 'chat'}）"
                    ),
                )
            from backend.services.generation.image_executors import (
                ExecutorError,
                resolve_executor,
            )

            provider = model.provider
            try:
                resolve_executor(
                    getattr(provider, "worker_type", None),
                    getattr(provider, "apiHost", None),
                )
            except ExecutorError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        elif model_type == "image":
            raise HTTPException(
                status_code=400,
                detail="该模型是生图模型，请把配置的后端类型改为「生图模型」",
            )
    elif not (mcp_server_id or "").strip():
        raise HTTPException(
            status_code=400, detail="后端类型为「MCP 服务」时必须绑定一个 MCP 服务"
        )


@router.get("/", response_model=List[ImageGenConfigResponse], summary="获取所有生图配置")
async def list_image_gen_configs(db: AsyncSession = Depends(get_db)):
    return await image_gen_crud.get_all_image_gen_configs(db)


@router.post(
    "/",
    response_model=ImageGenConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建生图配置",
)
async def create_image_gen_config(
    payload: ImageGenConfigCreate, db: AsyncSession = Depends(get_db)
):
    existing = await image_gen_crud.get_image_gen_config_by_name(db, payload.name)
    if existing:
        raise HTTPException(status_code=400, detail="配置名称已存在")
    return await image_gen_crud.create_image_gen_config(db, payload)


@router.get(
    "/{config_id}", response_model=ImageGenConfigResponse, summary="获取单个生图配置"
)
async def get_image_gen_config(config_id: str, db: AsyncSession = Depends(get_db)):
    config = await image_gen_crud.get_image_gen_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="生图配置不存在")
    return config


@router.put(
    "/{config_id}", response_model=ImageGenConfigResponse, summary="更新生图配置"
)
async def update_image_gen_config(
    config_id: str,
    payload: ImageGenConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    if payload.name:
        existing = await image_gen_crud.get_image_gen_config_by_name(db, payload.name)
        if existing and existing.id != config_id:
            raise HTTPException(status_code=400, detail="配置名称已存在")

    current = await image_gen_crud.get_image_gen_config(db, config_id)
    if not current:
        raise HTTPException(status_code=404, detail="生图配置不存在")

    standard_tools = (
        payload.enableStandardTools
        if payload.enableStandardTools is not None
        else current.enableStandardTools
    )
    generate_show = (
        payload.enableGenerateShow
        if payload.enableGenerateShow is not None
        else current.enableGenerateShow
    )
    if not standard_tools and not generate_show:
        raise HTTPException(
            status_code=400, detail="标准三件套与一条龙工具至少需要启用一个"
        )

    await _validate_backend_binding(db, current, payload)

    updated = await image_gen_crud.update_image_gen_config(db, config_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="生图配置不存在")
    return updated


@router.delete(
    "/{config_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除生图配置"
)
async def delete_image_gen_config(config_id: str, db: AsyncSession = Depends(get_db)):
    success = await image_gen_crud.delete_image_gen_config(db, config_id)
    if not success:
        raise HTTPException(status_code=404, detail="生图配置不存在")
    return


@router.post(
    "/{config_id}/test",
    response_model=ImageGenToolCheckResult,
    summary="检测生图后端是否可用（MCP 服务合规 / 模型可出图）",
)
async def test_image_gen_config(config_id: str, db: AsyncSession = Depends(get_db)):
    """检测绑定的后端。

    - ``mcp``：连接服务，检查三个标准工具是否齐全，并探测是否声明
      ``reference_images``（参考图能力）；
    - ``model``：校验模型与其服务商是否可用，并提示能力声明；
    - ``image_api``：校验生图模型与执行器，并 GET 探测端点 / 能力（不生成图片）。

    不合规仅作为提示返回，不阻止保存 —— 服务可能尚未启动。
    """
    from backend.services.generation.agent.image_gen.factory import (
        BACKEND_IMAGE_API,
        BACKEND_MODEL,
        check_mcp_image_service,
        check_reference_support,
        load_model_backend_config,
    )

    config = await image_gen_crud.get_image_gen_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="生图配置不存在")

    backend_type = (config.backendType or "mcp").strip().lower()

    if backend_type == BACKEND_IMAGE_API:
        return await _test_image_api_backend(db, config)
    if backend_type == BACKEND_MODEL:
        return await _test_model_backend(db, config, load_model_backend_config)

    found, missing, error = await check_mcp_image_service(db, config)
    supports_reference, _ = await check_reference_support(db, config)
    if error:
        return ImageGenToolCheckResult(
            status="unhealthy",
            backend_type=backend_type,
            found_tools=found,
            missing_tools=missing,
            supports_reference_images=supports_reference,
            message="连接失败",
            error=error,
        )

    if missing:
        return ImageGenToolCheckResult(
            status="unhealthy",
            backend_type=backend_type,
            found_tools=found,
            missing_tools=missing,
            supports_reference_images=supports_reference,
            message="MCP 服务缺少标准工具: " + ", ".join(missing),
        )

    reference_note = (
        "支持参考图" if supports_reference else "不支持参考图（image_generate 未声明 reference_images）"
    )
    return ImageGenToolCheckResult(
        status="healthy",
        backend_type=backend_type,
        server_name=config.name,
        found_tools=found,
        supports_reference_images=supports_reference,
        message=f"符合生图标准；{reference_note}",
    )


async def _test_model_backend(
    db: AsyncSession,
    config,
    loader,
) -> ImageGenToolCheckResult:
    """模型后端检测：只做配置与能力校验，不发真实生成请求（避免烧钱）。"""
    from backend.services.generation.agent.image_gen.factory import ImageGenConfigError

    try:
        info = await loader(db, config)
    except ImageGenConfigError as exc:
        return ImageGenToolCheckResult(
            status="unhealthy",
            backend_type="model",
            supports_reference_images=(
                True if config.supportsReferenceImages is None else bool(config.supportsReferenceImages)
            ),
            message="模型后端不可用",
            error=str(exc),
        )

    worker = str(info.get("worker_type") or "").lower()
    if worker not in ("google", "openai", "deepseek"):
        return ImageGenToolCheckResult(
            status="unhealthy",
            backend_type="model",
            supports_reference_images=True,
            message=(
                f"服务商类型 {worker!r} 没有可用的对话出图接口，"
                "仅 google / openai / deepseek 兼容网关支持"
            ),
        )

    supports_reference = (
        True if config.supportsReferenceImages is None else bool(config.supportsReferenceImages)
    )
    protocol = "google generateContent" if worker == "google" else "chat/completions"
    declared = info.get("declares_image_output")
    if declared:
        message = f"已绑定模型 {info.get('model_name')}（{worker} / {protocol}），声明可输出图片"
    else:
        message = (
            f"已绑定模型 {info.get('model_name')}（{worker} / {protocol}）；"
            "该模型的元数据未声明 output_modalities 含 image，"
            "若生成失败请确认模型本身是否支持出图"
        )
    return ImageGenToolCheckResult(
        status="healthy",
        backend_type="model",
        server_name=info.get("provider_name"),
        found_tools=["image_generate", "image_task_status", "image_download"],
        supports_reference_images=supports_reference,
        message=message,
    )


async def _test_image_api_backend(db: AsyncSession, config) -> ImageGenToolCheckResult:
    """纯生图后端检测：GET 探测端点与能力，不发真实生成请求（避免烧钱）。"""
    from backend.services.generation.agent.image_gen.factory import (
        ImageGenConfigError,
        probe_image_endpoint,
    )

    try:
        detail = await probe_image_endpoint(db, config)
    except ImageGenConfigError as exc:
        return ImageGenToolCheckResult(
            status="unhealthy",
            backend_type="image_api",
            supports_reference_images=(
                None
                if config.supportsReferenceImages is None
                else bool(config.supportsReferenceImages)
            ),
            message="生图模型后端不可用",
            error=str(exc),
        )

    capabilities = detail.get("capabilities") or {}
    declared = capabilities.get("supported_parameters")
    if isinstance(declared, dict):
        parameter_keys = sorted(declared)
    elif isinstance(declared, list):
        parameter_keys = sorted(str(key) for key in declared)
    else:
        parameter_keys = []

    paths = " / ".join(detail.get("paths") or [])
    reference_note = (
        "支持参考图" if detail.get("supports_reference_images") else "不支持参考图"
    )
    message = (
        f"已绑定模型 {detail.get('model_id')}（执行器 {detail.get('executor')} → {paths}）；"
        f"{reference_note}"
    )
    if parameter_keys:
        message += "；模型声明支持: " + ", ".join(parameter_keys)
    elif detail.get("declared"):
        message += "；接口未返回能力描述，参数将按执行器白名单下发"

    return ImageGenToolCheckResult(
        status="unhealthy" if detail.get("error") else "healthy",
        backend_type="image_api",
        server_name=detail.get("provider_name"),
        found_tools=["image_generate", "image_task_status", "image_download"],
        supports_reference_images=bool(detail.get("supports_reference_images")),
        executor=detail.get("executor"),
        capabilities=capabilities or None,
        message=message,
        error=detail.get("error"),
    )
