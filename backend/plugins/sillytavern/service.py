"""
SillyTavern 角色卡导入编排服务。

将拆分后的文件树落库为 Resource 树（文件夹 + FILE 资源）。
复用核心基础设施 FileService / resource_crud，本模块仅做业务编排。
"""

import logging
from typing import Optional

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.crud import resource_crud
from backend.exceptions import AppHTTPException
from backend.schemas.enums import ResourceItemType, ResourceType, FileManagementType
from backend.services.file_service import FileService
from backend.services.resource_service import delete_resource_tree, validate_name_uniqueness

from .detection import is_sillytavern_card_png
from .parser import SillyTavernCardError, parse_card
from .models import extract_card
from .splitter import split_card

logger = logging.getLogger(__name__)


class SillyTavernImportError(Exception):
    """SillyTavern 导入业务错误。"""


class SillyTavernImportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    async def import_png(self, file: UploadFile, parent_id: Optional[str]) -> schemas.Resource:
        """
        从上传的 PNG 文件导入 SillyTavern 角色卡，拆解为文件夹 + 多个 FILE 资源。

        Args:
            file: 上传的 PNG 文件。
            parent_id: 目标父文件夹 ID（'root' 表示根目录）。

        Returns:
            新建的角色文件夹 Resource。

        Raises:
            SillyTavernImportError: 不是角色卡、解析失败或同名冲突。
        """
        data = await file.read()
        if not is_sillytavern_card_png(data):
            raise SillyTavernImportError("不是 SillyTavern 角色卡 PNG")

        # 完整解析
        try:
            parsed = parse_card(data)
        except SillyTavernCardError as e:
            raise SillyTavernImportError(str(e))

        # 提取 + 拆分
        extracted = extract_card(parsed.card)
        split = split_card(extracted, parsed.avatar_bytes)

        # 同名冲突检查（error 策略）
        normalized_parent = None if parent_id == "root" else parent_id
        try:
            await validate_name_uniqueness(self.db, split.folder_name, normalized_parent)
        except HTTPException as e:
            raise SillyTavernImportError(
                f"同名角色 '{split.folder_name}' 已存在，导入中止：{e.detail}"
            )

        # 建角色文件夹
        folder_schema = schemas.ResourceCreate(
            name=split.folder_name,
            itemType=ResourceItemType.FOLDER,
            parentId=normalized_parent,
        )
        folder_res = await resource_crud.create_resource(self.db, folder_schema)

        try:
            await self._create_files(split.files, folder_res.id)
        except Exception:
            # 回滚：清理已建的角色树
            await self.db.rollback()
            try:
                await delete_resource_tree(self.db, folder_res.id)
            except Exception:
                pass
            raise

        await self.db.refresh(folder_res)
        return folder_res

    async def _create_files(self, files, folder_id: str) -> None:
        """将文件清单落库为 FILE 资源，支持子目录（sprites/）。"""
        # 子目录名 → 子文件夹 Resource 映射
        subfolders = {}

        for sf in files:
            # 判断是否有子目录
            if "/" in sf.rel_path:
                subdir = sf.rel_path.split("/", 1)[0]
                filename = sf.rel_path.split("/", 1)[1]
                if subdir not in subfolders:
                    sub_schema = schemas.ResourceCreate(
                        name=subdir,
                        itemType=ResourceItemType.FOLDER,
                        parentId=folder_id,
                    )
                    sub_res = await resource_crud.create_resource(self.db, sub_schema)
                    subfolders[subdir] = sub_res.id
                parent_id = subfolders[subdir]
            else:
                filename = sf.rel_path
                parent_id = folder_id

            # 保存文件内容
            db_file = await self.file_service.save_file_from_bytes(
                data=sf.data,
                filename=filename,
                mime_type=sf.mime_type,
                management_type=[FileManagementType.RESOURCE.value],
                sub_path="sillytavern",
            )

            file_schema = schemas.ResourceCreate(
                name=filename,
                itemType=ResourceItemType.RESOURCE,
                resourceType=ResourceType.FILE,
                parentId=parent_id,
                initial_content=db_file.id,
                initial_attributes={},
            )
            await resource_crud.create_resource(self.db, file_schema)
