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
    summary="检测绑定的 MCP 服务是否符合生图标准",
)
async def test_image_gen_config(config_id: str, db: AsyncSession = Depends(get_db)):
    """连接绑定的 MCP 服务，检查三个标准工具是否齐全。

    不合规仅作为提示返回，不阻止保存 —— 服务可能尚未启动。
    """
    from backend.services.generation.agent.image_gen.factory import (
        check_mcp_image_service,
    )

    config = await image_gen_crud.get_image_gen_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="生图配置不存在")

    found, missing, error = await check_mcp_image_service(db, config)
    if error:
        return ImageGenToolCheckResult(
            status="unhealthy",
            found_tools=found,
            missing_tools=missing,
            message="连接失败",
            error=error,
        )

    if missing:
        return ImageGenToolCheckResult(
            status="unhealthy",
            found_tools=found,
            missing_tools=missing,
            message="MCP 服务缺少标准工具: " + ", ".join(missing),
        )

    return ImageGenToolCheckResult(
        status="healthy",
        found_tools=found,
        message="符合生图标准",
    )
