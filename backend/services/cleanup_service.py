# backend/services/cleanup_service.py

import logging
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models import file_model, chat_model, setting_model, resource_model
from backend.schemas.enums import FileManagementType, ResourceType
from backend.services.file_service import FileService
from backend.config.timezone_config import get_configured_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPORARY_FILE_LIFETIME = timedelta(hours=24)


async def _cleanup_temporary_files(db: AsyncSession):
    """清理过期的临时文件"""
    cutoff_time = get_configured_now() - TEMPORARY_FILE_LIFETIME

    # 查找包含 temporary 类型的文件
    stmt = select(file_model.File).where(
        file_model.File.management_type.contains([FileManagementType.TEMPORARY.value]),
        file_model.File.created_at < cutoff_time
    )
    result = await db.execute(stmt)
    expired_files = result.scalars().all()

    if not expired_files:
        return

    logger.info(f"发现 {len(expired_files)} 个过期的临时文件，准备清理...")
    file_service = FileService(db)

    for f in expired_files:
        try:
            deleted = await file_service.remove_type_and_cleanup(f.id, FileManagementType.TEMPORARY.value)
            if deleted:
                logger.info(f"已删除临时文件: {f.filename} (ID: {f.id})")
            else:
                logger.info(f"已移除文件 {f.filename} (ID: {f.id}) 的临时类型标记")
        except Exception as e:
            logger.error(f"处理临时文件 {f.id} 时出错: {e}")


async def _cleanup_sub_message_files(db: AsyncSession):
    """清理与任何 SubMessage 都不再关联的文件"""
    # 获取所有正在被 SubMessage 引用的文件ID
    stmt_active = select(chat_model.SubMessage.content).where(
        chat_model.SubMessage.type == 'File'
    ).distinct()
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    # 获取所有包含 sub_message 类型的文件ID
    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.SUB_MESSAGE.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    # 找出差集，即孤儿文件
    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 SubMessage 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.SUB_MESSAGE.value)
            if deleted:
                logger.info(f"已删除孤儿 SubMessage 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的 sub_message 类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 SubMessage 文件 {file_id} 时出错: {e}")


async def _cleanup_global_setting_files(db: AsyncSession):
    """清理与任何全局设置（如头像）都不再关联的文件"""
    avatar_keys = ["user_avatar_file_id", "ai_avatar_file_id"]
    stmt_active = select(setting_model.GlobalSettings.value).where(
        setting_model.GlobalSettings.key.in_(avatar_keys),
        setting_model.GlobalSettings.value.isnot(None)
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.GLOBAL_SETTING.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 GlobalSetting 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.GLOBAL_SETTING.value)
            if deleted:
                logger.info(f"已删除孤儿 GlobalSetting 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的 global_setting 类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 GlobalSetting 文件 {file_id} 时出错: {e}")


async def _cleanup_resource_files(db: AsyncSession):
    """清理与任何 ResourceVersion 都不再关联的 RESOURCE 类型文件"""
    stmt_active = (
        select(resource_model.ResourceVersion.content)
        .join(resource_model.Resource, resource_model.ResourceVersion.resourceId == resource_model.Resource.id)
        .where(
            resource_model.Resource.resourceType.in_([ResourceType.FILE.value, ResourceType.KB_FILE.value]),
            resource_model.ResourceVersion.content.is_not(None)
        )
    )
    result_active = await db.execute(stmt_active)
    active_file_ids = {row[0] for row in result_active}

    stmt_managed = select(file_model.File.id).where(
        file_model.File.management_type.contains([FileManagementType.RESOURCE.value]) |
        file_model.File.management_type.contains([FileManagementType.KB_DOCUMENT.value])
    )
    result_managed = await db.execute(stmt_managed)
    managed_file_ids = {row[0] for row in result_managed}

    orphan_file_ids = managed_file_ids - active_file_ids

    if not orphan_file_ids:
        return

    logger.info(f"发现 {len(orphan_file_ids)} 个孤儿 Resource/KB 文件，准备清理...")
    file_service = FileService(db)

    for file_id in orphan_file_ids:
        try:
            deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.RESOURCE.value)

            if not deleted:
                deleted = await file_service.remove_type_and_cleanup(file_id, FileManagementType.KB_DOCUMENT.value)

            if deleted:
                logger.info(f"已删除孤儿 Resource/KB 文件 (ID: {file_id})")
            else:
                logger.info(f"已移除文件 {file_id} 的资源类型标记")
        except Exception as e:
            logger.error(f"处理孤儿 Resource 文件 {file_id} 时出错: {e}")


async def cleanup_zombie_files():
    """主清理函数，按顺序执行所有类型的僵尸文件清理。"""
    logger.info("开始执行僵尸文件清理任务...")

    try:
        async with AsyncSessionLocal() as db:
            await _cleanup_temporary_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_sub_message_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_global_setting_files(db)

        async with AsyncSessionLocal() as db:
            await _cleanup_resource_files(db)

        logger.info("僵尸文件清理任务执行完毕。")

    except Exception as e:
        logger.error(f"僵尸文件清理任务执行期间发生意外错误: {e}", exc_info=True)
