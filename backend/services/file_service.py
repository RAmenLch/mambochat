# backend/services/file_service.py

import urllib.parse
from typing import List, Optional, Union
from fastapi import UploadFile, HTTPException, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models.file_model import File
from backend.models.base_model import generate_uuid
from backend.crud import file_crud
from backend.services.storage_service import storage_service, LocalStorageService
from backend.utils.file_utils import FileUtils
from backend import schemas


class FileService:
    """
    统一文件服务层，作为整个后端所有文件操作的唯一入口。
    屏蔽底层存储差异，集中管理文件的生命周期、防呆回滚与双引擎路由。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def convert_to_schema(self, db_file: File) -> schemas.File:
        """
        将 File 模型对象转换为 schemas.File 响应对象。
        统一处理 editable 字段判定和 URL 生成。
        """
        return schemas.File(
            id=db_file.id,
            filename=db_file.filename,
            mime_type=db_file.mime_type,
            size=db_file.size,
            created_at=db_file.created_at,
            url=self.get_url(db_file.storage_path),
            editable=(db_file.storage_type == 'db')
        )

    async def save_file(
            self,
            file: UploadFile,
            management_type: List[str],
            sub_path: str = "uploads"
    ) -> File:
        sample = await file.read(8192)
        await file.seek(0)

        mime_type = FileUtils.correct_mime_type(file.filename, file.content_type, sample)
        if not FileUtils.is_allowed_mime_type(mime_type):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {mime_type}。")

        file_id = generate_uuid()
        file_size = file.size

        if FileUtils.is_small_text_file(file_size, mime_type):
            data = await file.read()
            try:
                text_content = FileUtils.decode_to_utf8(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            db_file = File(
                id=file_id,
                filename=file.filename,
                storage_path=f"virtual_db_{file_id}",
                mime_type=mime_type,
                size=file_size,
                storage_type='db',
                content=text_content,
                management_type=management_type
            )
            return await self._commit_file_record(db_file)
        else:
            try:
                storage_path = await storage_service.save(file, sub_path=sub_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"文件存储失败: {e}")

            db_file = File(
                id=file_id,
                filename=file.filename,
                storage_path=storage_path,
                mime_type=mime_type,
                size=file_size,
                storage_type='local',
                management_type=management_type
            )
            return await self._commit_file_record(db_file, physical_path_to_rollback=storage_path)

    async def save_file_from_bytes(
            self,
            data: bytes,
            filename: str,
            mime_type: str,
            management_type: List[str],
            sub_path: str = "chat_attachments",
            file_id: Optional[str] = None
    ) -> File:
        sample = data[:8192]
        final_mime_type = FileUtils.correct_mime_type(filename, mime_type, sample)

        if not FileUtils.is_allowed_mime_type(final_mime_type):
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {final_mime_type}。")

        final_id = file_id or generate_uuid()
        file_size = len(data)

        if FileUtils.is_small_text_file(file_size, final_mime_type):
            try:
                text_content = FileUtils.decode_to_utf8(data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            db_file = File(
                id=final_id,
                filename=filename,
                storage_path=f"virtual_db_{final_id}",
                mime_type=final_mime_type,
                size=file_size,
                storage_type='db',
                content=text_content,
                management_type=management_type
            )
            return await self._commit_file_record(db_file)
        else:
            try:
                storage_path = await storage_service.save_from_bytes(data, filename, sub_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"文件存储失败: {e}")

            db_file = File(
                id=final_id,
                filename=filename,
                storage_path=storage_path,
                mime_type=final_mime_type,
                size=file_size,
                storage_type='local',
                management_type=management_type
            )
            return await self._commit_file_record(db_file, physical_path_to_rollback=storage_path)

    async def _commit_file_record(self, db_file: File, physical_path_to_rollback: Optional[str] = None) -> File:
        try:
            self.db.add(db_file)
            await self.db.commit()
            await self.db.refresh(db_file)
            return db_file
        except Exception as e:
            await self.db.rollback()
            if physical_path_to_rollback:
                await storage_service.delete(physical_path_to_rollback)
            raise HTTPException(status_code=500, detail=f"数据库保存失败: {e}")

    async def get_file_content(self, file_id: str) -> bytes:
        file = await self.get_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        if file.storage_type == 'db':
            return (file.content or "").encode('utf-8')
        else:
            try:
                return await storage_service.read_bytes(file.storage_path)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Physical file not found")

    async def get_text_content(self, file_id: str) -> str:
        """
        获取文件的文本内容。
        仅支持 storage_type 为 'db' 的文件，以确保安全性和性能。
        """
        file = await self.get_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        if file.storage_type != 'db':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content retrieval is only supported for database-stored text files."
            )

        return file.content or ""

    async def get_file_for_download(self, storage_path: str) -> Union[Response, FileResponse]:
        file = await self.get_file_by_path(storage_path)
        if not file:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found in database.")

        encoded_filename = urllib.parse.quote(file.filename)

        if file.storage_type == 'db':
            headers = {"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
            return Response(
                content=(file.content or "").encode('utf-8'),
                media_type=file.mime_type,
                headers=headers
            )
        else:
            if not isinstance(storage_service, LocalStorageService):
                raise HTTPException(status_code=501, detail="Download not implemented for current storage type.")

            base_path = storage_service.base_path.resolve()
            file_path = (base_path / file.storage_path).resolve()

            if not str(file_path).startswith(str(base_path)) or not file_path.is_file():
                raise HTTPException(status_code=404, detail="Physical file not found or access forbidden.")

            return FileResponse(
                path=file_path,
                media_type=file.mime_type,
                filename=file.filename
            )

    async def edit_file(self, file_id: str, new_content: str) -> File:
        file = await self.get_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        if file.storage_type == 'local':
            raise HTTPException(status_code=400, detail="本地文件不支持直接编辑")

        content_bytes = new_content.encode('utf-8')
        if len(content_bytes) > 262144:
            raise HTTPException(status_code=400, detail="编辑后的文本超出大小限制")

        file.content = new_content
        file.size = len(content_bytes)

        self.db.add(file)
        await self.db.commit()
        await self.db.refresh(file)
        return file

    async def delete_file(self, file_id: str) -> None:
        file = await self.get_file(file_id)
        if not file:
            return

        if file.storage_type == 'local':
            await storage_service.delete(file.storage_path)

        await self.db.delete(file)
        await self.db.commit()

    async def get_file(self, file_id: str) -> Optional[File]:
        return await file_crud.get_file(self.db, file_id)

    async def get_file_by_path(self, storage_path: str) -> Optional[File]:
        return await file_crud.get_file_by_storage_path(self.db, storage_path)

    async def batch_get_files(self, file_ids: List[str]) -> List[File]:
        return await file_crud.get_files_by_ids(self.db, file_ids)

    def get_url(self, storage_path: str) -> str:
        return f"/api/files/download/{storage_path}"

    async def update_management_type(self, file_id: str, new_type: str, merge: bool = True) -> Optional[File]:
        return await file_crud.update_file_management_type(self.db, file_id, new_type, merge)

    async def remove_type_and_cleanup(self, file_id: str, type_to_remove: str) -> bool:
        file = await self.get_file(file_id)
        if not file or not file.management_type:
            return False

        current_types = list(file.management_type)
        if type_to_remove in current_types:
            current_types.remove(type_to_remove)

            if not current_types:
                await self.delete_file(file_id)
                return True
            else:
                file.management_type = current_types
                self.db.add(file)
                await self.db.commit()
                return False

        return False
