# backend/crud/image_gen_crud.py

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.image_gen_model import ImageGenConfig
from backend.schemas.image_gen import ImageGenConfigCreate, ImageGenConfigUpdate


async def get_image_gen_config(db: AsyncSession, config_id: str) -> Optional[ImageGenConfig]:
    result = await db.execute(select(ImageGenConfig).filter(ImageGenConfig.id == config_id))
    return result.scalar_one_or_none()


async def get_image_gen_config_by_name(db: AsyncSession, name: str) -> Optional[ImageGenConfig]:
    result = await db.execute(select(ImageGenConfig).filter(ImageGenConfig.name == name))
    return result.scalar_one_or_none()


async def get_all_image_gen_configs(db: AsyncSession) -> List[ImageGenConfig]:
    result = await db.execute(select(ImageGenConfig).order_by(ImageGenConfig.createdAt))
    return list(result.scalars().all())


async def get_enabled_image_gen_configs(db: AsyncSession) -> List[ImageGenConfig]:
    result = await db.execute(
        select(ImageGenConfig).filter(ImageGenConfig.isEnabled == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def create_image_gen_config(
    db: AsyncSession, payload: ImageGenConfigCreate
) -> ImageGenConfig:
    db_obj = ImageGenConfig(**payload.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_image_gen_config(
    db: AsyncSession, config_id: str, payload: ImageGenConfigUpdate
) -> Optional[ImageGenConfig]:
    db_obj = await get_image_gen_config(db, config_id)
    if not db_obj:
        return None

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def delete_image_gen_config(db: AsyncSession, config_id: str) -> bool:
    db_obj = await get_image_gen_config(db, config_id)
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
