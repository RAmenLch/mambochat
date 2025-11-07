# backend/crud/file_crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from ..models import file_model

async def create_file(
    db: AsyncSession,
    filename: str,
    storage_path: str,
    mime_type: str,
    size: int
) -> file_model.File:
    """
    在数据库中创建一条新的文件元数据记录。

    :param db: 数据库会话。
    :param filename: 原始文件名。
    :param storage_path: 存储系统中的相对路径。
    :param mime_type: 文件的MIME类型。
    :param size: 文件大小（字节）。
    :return: 创建的File对象。
    """
    db_file = file_model.File(
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        size=size
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
