# backend/crud/file_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List

from backend.models import file_model
from backend.models.base_model import generate_uuid


async def create_file(
        db: AsyncSession,
        filename: str,
        storage_path: str,
        mime_type: str,
        size: int,
        management_type: List[str],  # 改为列表类型
        file_id: Optional[str] = None
) -> file_model.File:
    """
    在数据库中创建一条新的文件元数据记录。
    management_type 现在是一个列表。
    """
    final_id = file_id or generate_uuid()
    db_file = file_model.File(
        id=final_id,
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        size=size,
        management_type=management_type
    )
    db.add(db_file)
    await db.commit()
    await db.refresh(db_file)
    return db_file


async def get_file(db: AsyncSession, file_id: str) -> Optional[file_model.File]:
    """通过ID从数据库中获取文件元数据。"""
    if not file_id:
        return None
    result = await db.execute(select(file_model.File).filter(file_model.File.id == file_id))
    return result.scalars().first()


async def get_file_by_storage_path(db: AsyncSession, path: str) -> Optional[file_model.File]:
    """通过 storage_path 从数据库中获取文件元数据。"""
    if not path:
        return None
    result = await db.execute(select(file_model.File).filter(file_model.File.storage_path == path))
    return result.scalars().first()


async def delete_file(db: AsyncSession, file_id: str) -> Optional[file_model.File]:
    """
    通过ID从数据库中删除文件元数据记录。
    此函数仅删除数据库记录，不删除物理文件。
    """
    db_file = await get_file(db, file_id)
    if db_file:
        await db.delete(db_file)
        await db.commit()
    return db_file


async def update_file_management_type(
        db: AsyncSession,
        file_id: str,
        new_type: str,
        merge: bool = True
) -> Optional[file_model.File]:
    """
    智能更新文件的管理类型。

    如果 merge=True:
        - 如果文件是临时类型，则移除临时标记，加入新类型
        - 如果文件是非临时类型，则合并新旧类型（避免重复）
    如果 merge=False:
        - 直接替换整个类型列表

    :param db: 数据库会话
    :param file_id: 要更新的文件ID
    :param new_type: 新的管理类型
    :param merge: 是否合并到现有类型列表中
    :return: 更新后的File对象或None
    """
    db_file = await get_file(db, file_id)
    if not db_file:
        return None

    if merge:
        # 确保类型列表存在
        if not db_file.management_type:
            db_file.management_type = []

        # 如果当前是临时类型，先移除临时标记
        if 'temporary' in db_file.management_type:
            db_file.management_type.remove('temporary')

        # 添加新类型（避免重复）
        if new_type not in db_file.management_type:
            db_file.management_type.append(new_type)
    else:
        # 直接替换整个列表
        db_file.management_type = [new_type]

    await db.commit()
    await db.refresh(db_file)
    return db_file


async def remove_file_management_type(
        db: AsyncSession,
        file_id: str,
        type_to_remove: str
) -> Optional[file_model.File]:
    """
    从文件的管理类型列表中移除指定的类型。
    如果移除后类型列表为空，则不会删除文件，需要调用者判断。

    :param db: 数据库会话
    :param file_id: 文件ID
    :param type_to_remove: 要移除的类型
    :return: 更新后的File对象或None
    """
    db_file = await get_file(db, file_id)
    if db_file and db_file.management_type:
        if type_to_remove in db_file.management_type:
            db_file.management_type.remove(type_to_remove)
            await db.commit()
            await db.refresh(db_file)
    return db_file


async def get_files_by_ids(db: AsyncSession, file_ids: List[str]) -> List[file_model.File]:
    """通过ID列表批量获取文件元数据。"""
    if not file_ids:
        return []
    result = await db.execute(select(file_model.File).filter(file_model.File.id.in_(file_ids)))
    return result.scalars().all()
