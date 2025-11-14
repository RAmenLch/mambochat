# backend/routers/file_management.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.storage_service import storage_service, LocalStorageService
from ..database import get_db
from ..crud import file_crud
from .. import schemas
from ..schemas.enums import FileManagementType

router = APIRouter(
    prefix="/api/files",
    tags=["File Management"]
)

# 定义允许上传的文件类型和最大大小
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_MIME_TYPES = {
    # ... (此处省略，内容不变)
    "text/plain", "text/markdown", "image/jpeg", "image/png", "image/gif", "image/webp",
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/webm", "video/mp4", "video/webm",
    "application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/json", "text/xml", "application/xml", "text/csv", "text/x-python",
    "application/javascript", "text/css", "text/html", "application/x-yaml",
}


@router.post(
    "/upload",
    response_model=schemas.File,
    summary="上传临时文件"
)
async def upload_temporary_file(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    # ... (此函数内容不变)
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大。最大允许 {MAX_FILE_SIZE // 1024 // 1024} MB。"
        )
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file.content_type}。"
        )
    try:
        storage_path = await storage_service.save(file, sub_path="chat_attachments")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件存储失败: {e}"
        )
    db_file = await file_crud.create_file(
        db=db,
        filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        size=file.size,
        management_type=FileManagementType.TEMPORARY.value
    )
    return schemas.File(
        id=db_file.id,
        filename=db_file.filename,
        mime_type=db_file.mime_type,
        size=db_file.size,
        created_at=db_file.created_at,
        url=storage_service.get_url(db_file.storage_path)
    )


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
    # 1. 使用新的 CRUD 函数通过 storage_path 获取文件元数据
    db_file = await file_crud.get_file_by_storage_path(db, path=storage_path)
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found in database."
        )

    # 2. 检查物理文件是否存在 (作为安全校验)
    if not isinstance(storage_service, LocalStorageService):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Download not implemented for the current storage service type."
        )

    base_path = storage_service.base_path.resolve()
    file_path = (base_path / db_file.storage_path).resolve()

    if not str(file_path).startswith(str(base_path)) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found or access forbidden."
        )

    # 3. 使用数据库中的元数据构建 FileResponse
    return FileResponse(
        path=file_path,
        media_type=db_file.mime_type,
        filename=db_file.filename  # FastAPI 会自动处理 Content-Disposition
    )

