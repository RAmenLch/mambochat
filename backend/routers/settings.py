# backend/routers/settings.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any, Optional

from ..crud import setting_crud, provider_crud
from ..services import provider_service
from ..models import setting_model
from .. import schemas
from ..database import get_db

router = APIRouter()


def _get_typed_setting(setting: Optional[schemas.GlobalSetting], default: Any, target_type: type) -> Any:
    """从数据库配置项安全地获取指定类型的值，如果不存在或转换失败则返回默认值"""
    if setting and setting.value is not None:
        try:
            if target_type == bool:
                return setting.value.lower() == 'true'
            return target_type(setting.value)
        except (ValueError, TypeError):
            return default
    return default


@router.get(
    "/settings/global",
    response_model=schemas.GlobalSettingsUpdate,
    summary="获取全局配置"
)
async def get_global_settings(db: AsyncSession = Depends(get_db)):
    """
    获取系统当前的全局配置。
    如果用户未设置过某些配置，则返回系统预设的默认值。
    """
    keys = [
        "default_model_id", "title_generation_model_id", "last_selected_provider_id",
        "default_max_context_messages", "default_temperature", "default_top_p",
        "default_stream", "proxy_enabled", "proxy_url"
    ]

    result = await db.execute(
        select(setting_model.GlobalSettings).filter(setting_model.GlobalSettings.key.in_(keys))
    )
    settings_map = {s.key: s for s in result.scalars().all()}

    default_model_id = _get_typed_setting(settings_map.get("default_model_id"), None, str)
    title_generation_model_id = _get_typed_setting(settings_map.get("title_generation_model_id"), None, str)
    last_selected_provider_id = _get_typed_setting(settings_map.get("last_selected_provider_id"), None, str)
    max_context = _get_typed_setting(settings_map.get("default_max_context_messages"), 0, int)
    temperature = _get_typed_setting(settings_map.get("default_temperature"), 1.0, float)
    top_p = _get_typed_setting(settings_map.get("default_top_p"), 1.0, float)
    stream = _get_typed_setting(settings_map.get("default_stream"), True, bool)
    proxy_enabled = _get_typed_setting(settings_map.get("proxy_enabled"), False, bool)
    proxy_url = _get_typed_setting(settings_map.get("proxy_url"), None, str)

    return schemas.GlobalSettingsUpdate(
        default_model_id=default_model_id,
        title_generation_model_id=title_generation_model_id,
        last_selected_provider_id=last_selected_provider_id,
        default_max_context_messages=max_context,
        default_temperature=temperature,
        default_top_p=top_p,
        default_stream=stream,
        proxy_enabled=proxy_enabled,
        proxy_url=proxy_url
    )


@router.put(
    "/settings/global",
    response_model=schemas.GlobalSettingsUpdate,
    summary="更新全局配置"
)
async def update_global_settings(
        settings_update: schemas.GlobalSettingsUpdate,
        db: AsyncSession = Depends(get_db)
):
    """
    更新系统的全局配置。
    """
    update_data = settings_update.model_dump(exclude_unset=True)
    settings_to_update = []

    if "default_model_id" in update_data:
        model_id = update_data["default_model_id"]
        if model_id:
            db_model = await provider_crud.get_model(db, model_id=model_id)
            if not db_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"模型ID '{model_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="default_model_id", value=model_id))

    if "title_generation_model_id" in update_data:
        model_id = update_data["title_generation_model_id"]
        if model_id:
            db_model = await provider_crud.get_model(db, model_id=model_id)
            if not db_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"标题生成模型ID '{model_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="title_generation_model_id", value=model_id))

    if "last_selected_provider_id" in update_data:
        provider_id = update_data["last_selected_provider_id"]
        if provider_id:
            db_provider = await provider_crud.get_provider(db, provider_id=provider_id)
            if not db_provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"服务商ID '{provider_id}' 不存在。"
                )
        settings_to_update.append(schemas.GlobalSetting(key="last_selected_provider_id", value=provider_id))

    param_keys = [
        "default_max_context_messages", "default_temperature", "default_top_p",
        "default_stream", "proxy_enabled", "proxy_url"
    ]
    for key in param_keys:
        if key in update_data:
            value = update_data[key]
            settings_to_update.append(schemas.GlobalSetting(key=key, value=str(value) if value is not None else None))

    for setting in settings_to_update:
        await setting_crud.update_setting(db, setting=setting)

    return await get_global_settings(db)


@router.post(
    "/settings/test-proxy",
    response_model=schemas.ConnectionTestResponse,
    summary="测试代理连接"
)
async def test_proxy(
    proxy_url: str = Body(..., embed=True),
    test_url: str = Body(..., embed=True)
):
    """
    通过指定的代理服务器访问一个测试URL，以验证代理的连通性。
    """
    if not proxy_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proxy URL cannot be empty.")
    if not test_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test URL cannot be empty.")

    return await provider_service.test_proxy_connection(proxy_url, test_url)

