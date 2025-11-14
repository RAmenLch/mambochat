# backend/crud/file_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List

from ..models import file_model


# --- 修改函数 ---
async def create_file(
        db: AsyncSession,
        filename: str,
        storage_path: str,
        mime_type: str,
        size: int,
        management_type: str
) -> file_model.File:
    """
    在数据库中创建一条新的文件元数据记录。

    :param db: 数据库会话。
    :param filename: 原始文件名。
    :param storage_path: 存储系统中的相对路径。
    :param mime_type: 文件的MIME类型。
    :param size: 文件大小（字节）。
    :param management_type: 文件的管理类型 (e.g., 'temporary', 'sub_message')。
    :return: 创建的File对象。
    """
    db_file = file_model.File(
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
    """
    通过ID从数据库中获取文件元数据。

    :param db: 数据库会话。
    :param file_id: 文件ID。
    :return: File对象或None。
    """
    if not file_id:
        return None
    result = await db.execute(select(file_model.File).filter(file_model.File.id == file_id))
    return result.scalars().first()


# +++ 新增函数 +++
async def get_file_by_storage_path(db: AsyncSession, path: str) -> Optional[file_model.File]:
    """
    通过 storage_path 从数据库中获取文件元数据。

    :param db: 数据库会话。
    :param path: 文件的存储路径。
    :return: File对象或None。
    """
    if not path:
        return None
    result = await db.execute(select(file_model.File).filter(file_model.File.storage_path == path))
    return result.scalars().first()


async def delete_file(db: AsyncSession, file_id: str) -> Optional[file_model.File]:
    """
    通过ID从数据库中删除文件元数据记录。
    此函数仅删除数据库记录，不删除物理文件。

    :param db: 数据库会话。
    :param file_id: 文件ID。
    :return: 被删除的File对象或None，以便调用者可以获取其storage_path。
    """
    db_file = await get_file(db, file_id)
    if db_file:
        await db.delete(db_file)
        await db.commit()
    return db_file


async def update_file_management_type(
        db: AsyncSession,
        file_id: str,
        new_type: str
) -> Optional[file_model.File]:
    """
    更新指定文件的管理类型。

    :param db: 数据库会话。
    :param file_id: 要更新的文件ID。
    :param new_type: 新的管理类型。
    :return: 更新后的File对象或None。
    """
    db_file = await get_file(db, file_id)
    if db_file:
        db_file.management_type = new_type
        await db.commit()
        await db.refresh(db_file)
    return db_file


async def get_files_by_ids(db: AsyncSession, file_ids: List[str]) -> List[file_model.File]:
    """
    通过ID列表批量获取文件元数据。

    :param db: 数据库会话。
    :param file_ids: 文件ID列表。
    :return: File对象列表。
    """
    if not file_ids:
        return []

    result = await db.execute(select(file_model.File).filter(file_model.File.id.in_(file_ids)))
    return result.scalars().all()

