# backend/crud/setting_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional,List

from backend.models import setting_model
from backend import schemas

async def get_setting(db: AsyncSession, key: str) -> Optional[setting_model.GlobalSettings]:
    """通过键获取单个全局配置项"""
    result = await db.execute(select(setting_model.GlobalSettings).filter(setting_model.GlobalSettings.key == key))
    return result.scalars().first()

async def get_all_settings(db: AsyncSession) -> List[setting_model.GlobalSettings]:
    """通过键获取单个全局配置项"""
    result = await db.execute(select(setting_model.GlobalSettings))
    return result.scalars().all()


async def update_setting(db: AsyncSession, setting: schemas.GlobalSetting) -> setting_model.GlobalSettings:
    """更新或创建(upsert)一个全局配置项"""
    db_setting = await get_setting(db, setting.key)
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = setting_model.GlobalSettings(**setting.model_dump())
        db.add(db_setting)
    await db.commit()
    await db.refresh(db_setting)
    return db_setting

