# backend/services/cleanup_service.py

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models import file_model, chat_model, setting_model, resource_model
from backend.schemas.enums import FileManagementType, ResourceType
from backend.services.storage_service import storage_service

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义临时文件的最长存活时间
TEMPORARY_FILE_LIFETIME = timedelta(hours=24)


async def _cleanup_temporary_files(db: AsyncSession):
    """清理过期的临时文件"""
    cutoff_time = datetime.now(timezone.utc) - TEMPORARY_FILE_LIFETIME

    # SQLAlchemy 2.0 style select
    stmt = select(file_model.File).where(
        file_model.File.management_type == FileManagementType.TEMPORARY.value,
        file_model.File.created_at < cutoff_time
    )
    result = await db.execute(stmt)
    expired_files = result.scalars().all()

    if not expired_files:
        return

    logger.info(f"发现 {len(expired_files)} 个过期的临时文件，准备清理...")
    for f in expired_files:
        try:
            await storage_service.delete(f.storage_path)
            await db.delete(f)
            logger.info(f"已删除临时文件: {f.filename} (ID: {f.id})")
        except Exception as e:
            logger.error(f"删除临时文件 {f.id} 时出错: {e}")

    await db.commit()


async def _cleanup_sub_message_files(db: AsyncSession):
    """清理与任何 SubMessage 都不再关联的文件"""
    # 1. 获取所有正在被 SubMessage 引用的文件ID
    stmt_active = select(chat_model.SubMessage.content).where(
        chat_model.SubMessage.type == 'File'
    ).distinct()
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    # 2. 获取所有标记为 SUB_MESSAGE 的文件ID
    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type == FileManagementType.SUB_MESSAGE.value
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    # 3. 找出差集，即孤儿文件
    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 SubMessage 文件，准备清理...")

    # 4. 删除孤儿文件记录和物理文件
    stmt_orphans = select(file_model.File).where(file_model.File.id.in_(orphan_file_ids))
    result_orphans = await db.execute(stmt_orphans)
    files_to_delete = result_orphans.scalars().all()

    for f in files_to_delete:
        try:
            await storage_service.delete(f.storage_path)
            await db.delete(f)
            logger.info(f"已删除孤儿 SubMessage 文件: {f.filename} (ID: {f.id})")
        except Exception as e:
            logger.error(f"删除孤儿 SubMessage 文件 {f.id} 时出错: {e}")

    await db.commit()


async def _cleanup_global_setting_files(db: AsyncSession):
    """清理与任何全局设置（如头像）都不再关联的文件"""
    # 1. 获取所有正在被设置引用的文件ID
    avatar_keys = ["user_avatar_file_id", "ai_avatar_file_id"]
    stmt_active = select(setting_model.GlobalSettings.value).where(
        setting_model.GlobalSettings.key.in_(avatar_keys),
        setting_model.GlobalSettings.value.isnot(None)
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    # 2. 获取所有标记为 GLOBAL_SETTING 的文件ID
    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type == FileManagementType.GLOBAL_SETTING.value
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    # 3. 找出差集，即孤儿文件
    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 GlobalSetting 文件（旧头像），准备清理...")

    # 4. 删除孤儿文件记录和物理文件
    stmt_orphans = select(file_model.File).where(file_model.File.id.in_(orphan_file_ids))
    result_orphans = await db.execute(stmt_orphans)
    files_to_delete = result_orphans.scalars().all()

    for f in files_to_delete:
        try:
            await storage_service.delete(f.storage_path)
            await db.delete(f)
            logger.info(f"已删除孤儿 GlobalSetting 文件: {f.filename} (ID: {f.id})")
        except Exception as e:
            logger.error(f"删除孤儿 GlobalSetting 文件 {f.id} 时出错: {e}")

    await db.commit()


async def _cleanup_kb_document_files(db: AsyncSession):
    """
    清理与任何 ResourceVersion 都不再关联的 KB_DOCUMENT 文件。
    KB 文件的 file_id 存储在 ResourceVersion.content 字段中。
    """
    # 1. 获取所有正在被 ResourceVersion 引用的文件ID
    # 我们只关心 ResourceType 为 KB_FILE 的资源对应的版本
    stmt_active = (
        select(resource_model.ResourceVersion.content)
        .join(resource_model.Resource, resource_model.ResourceVersion.resourceId == resource_model.Resource.id)
        .where(
            resource_model.Resource.resourceType == ResourceType.KB_FILE.value,
            resource_model.ResourceVersion.content.is_not(None)
        )
    )
    result_active = await db.execute(stmt_active)
    # 注意：content 字段存储的是 file_id 字符串
    active_file_ids = {row[0] for row in result_active}

    # 2. 获取所有标记为 KB_DOCUMENT 的文件ID
    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type == FileManagementType.KB_DOCUMENT.value
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    # 3. 找出差集，即孤儿文件
    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 KB_DOCUMENT 文件，准备清理...")

    # 4. 删除孤儿文件记录和物理文件
    stmt_orphans = select(file_model.File).where(file_model.File.id.in_(orphan_file_ids))
    result_orphans = await db.execute(stmt_orphans)
    files_to_delete = result_orphans.scalars().all()

    for f in files_to_delete:
        try:
            await storage_service.delete(f.storage_path)
            await db.delete(f)
            logger.info(f"已删除孤儿 KB 文件: {f.filename} (ID: {f.id})")
        except Exception as e:
            logger.error(f"删除孤儿 KB 文件 {f.id} 时出错: {e}")

    await db.commit()


async def cleanup_zombie_files():
    """
    主清理函数，按顺序执行所有类型的僵尸文件清理。
    此函数由后台调度器 (apscheduler) 定期调用。
    """
    logger.info("开始执行僵尸文件清理任务...")

    try:
        # 每个清理任务使用独立的数据库会话，以隔离潜在的失败
        async with AsyncSessionLocal() as db:
            await _cleanup_temporary_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_sub_message_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_global_setting_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_kb_document_files(db)

        logger.info("僵尸文件清理任务执行完毕。")

    except Exception as e:
        logger.error(f"僵尸文件清理任务执行期间发生意外错误: {e}", exc_info=True)
