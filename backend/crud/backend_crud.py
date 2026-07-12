from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from backend.models.backend_model import BackendConfig
from backend.schemas.backend import BackendConfigCreate, BackendConfigUpdate


async def get_backend(db: AsyncSession, backend_id: str) -> Optional[BackendConfig]:
    result = await db.execute(select(BackendConfig).filter(BackendConfig.id == backend_id))
    return result.scalars().first()


async def get_backends_by_ids(db: AsyncSession, backend_ids: List[str]) -> List[BackendConfig]:
    if not backend_ids:
        return []
    result = await db.execute(select(BackendConfig).filter(BackendConfig.id.in_(backend_ids)))
    items_map = {item.id: item for item in result.scalars().all()}
    # Preserve the caller's order — SQL IN does not guarantee order.
    return [items_map[bid] for bid in backend_ids if bid in items_map]


async def get_all_backends(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[BackendConfig]:
    result = await db.execute(select(BackendConfig).offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_backend(db: AsyncSession, backend_in: BackendConfigCreate) -> BackendConfig:
    db_obj = BackendConfig(**backend_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def update_backend(db: AsyncSession, backend_id: str, backend_in: BackendConfigUpdate) -> Optional[BackendConfig]:
    db_obj = await get_backend(db, backend_id)
    if not db_obj:
        return None

    update_data = backend_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def delete_backend(db: AsyncSession, backend_id: str) -> bool:
    db_obj = await get_backend(db, backend_id)
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
