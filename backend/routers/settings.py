# backend/routers/settings.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, schemas
from ..database import get_db

router = APIRouter()


@router.get(
    "/settings/global",
    response_model=schemas.GlobalSettingsUpdate,
    summary="获取全局配置"
)
async def get_global_settings(db: AsyncSession = Depends(get_db)):
    """
    获取系统当前的全局配置，包括默认模型和最后选择的服务商。
    """
    default_model_setting = await crud.get_setting(db, key="default_model_id")
    last_selected_provider_setting = await crud.get_setting(db, key="last_selected_provider_id")

    return schemas.GlobalSettingsUpdate(
        default_model_id=default_model_setting.value if default_model_setting else None,
        last_selected_provider_id=last_selected_provider_setting.value if last_selected_provider_setting else None
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

    if "default_model_id" in update_data:
        model_id = update_data["default_model_id"]
        if model_id:
            db_model = await crud.get_model(db, model_id=model_id)
            if not db_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"模型ID '{model_id}' 不存在。"
                )
        await crud.update_setting(db, setting=schemas.GlobalSetting(
            key="default_model_id",
            value=model_id
        ))

    if "last_selected_provider_id" in update_data:
        provider_id = update_data["last_selected_provider_id"]
        if provider_id:
            db_provider = await crud.get_provider(db, provider_id=provider_id)
            if not db_provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"服务商ID '{provider_id}' 不存在。"
                )
        await crud.update_setting(db, setting=schemas.GlobalSetting(
            key="last_selected_provider_id",
            value=provider_id
        ))

    return await get_global_settings(db)
