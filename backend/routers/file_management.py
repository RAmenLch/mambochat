# backend/routers/file_management.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend import schemas
from backend.schemas.enums import FileManagementType
from backend.services.file_service import FileService

router = APIRouter(
    prefix="/api/files",
    tags=["File Management"]
)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post(
    "/upload",
    response_model=schemas.File,
    summary="上传临时文件"
)
async def upload_temporary_file(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)

    db_file = await file_service.save_file(
        file=file,
        management_type=[FileManagementType.TEMPORARY.value],
        sub_path="chat_attachments",
        max_size=MAX_FILE_SIZE
    )

    return file_service.convert_to_schema(db_file)


@router.get(
    "/{file_id}/content",
    response_model=schemas.FileContentResponse,
    summary="获取文件文本内容"
)
async def get_file_text_content(file_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取文件的文本内容，仅支持数据库存储的小型文本文件。
    """
    file_service = FileService(db)
    content = await file_service.get_text_content(file_id)
    return schemas.FileContentResponse(content=content)


@router.put(
    "/{file_id}",
    response_model=schemas.File,
    summary="编辑文件内容"
)
async def edit_file_content(
        file_id: str,
        data: schemas.FileUpdate,
        db: AsyncSession = Depends(get_db)
):
    file_service = FileService(db)
    updated_file = await file_service.edit_file(file_id, data.content)
    return file_service.convert_to_schema(updated_file)


@router.get(
    "/download/{storage_path:path}",
    summary="获取/下载文件",
    responses={
        200: {"content": {"image/*": {}, "application/octet-stream": {}}},
        404: {"description": "File not found"},
    }
)
async def download_file(storage_path: str, db: AsyncSession = Depends(get_db)):
    """
    根据文件的存储路径提供文件访问，并使用原始文件名进行下载。
    """
    file_service = FileService(db)
    return await file_service.get_file_for_download(storage_path)
