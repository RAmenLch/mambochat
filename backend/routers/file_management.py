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
    # 文本文件
    "text/plain", "text/markdown",
    # 图片
    "image/jpeg", "image/png", "image/gif", "image/webp",
    # 音频
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/webm",
    # 视频
    "video/mp4", "video/webm",
    # 办公文件
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    # 代码/数据
    "application/json", "text/xml", "application/xml", "text/csv",
    "text/x-python", "application/javascript", "text/css", "text/html",
    "application/x-yaml",
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
    """
    处理文件上传。文件首先作为临时文件存储，等待被消息引用。
    """
    # 1. 校验文件大小
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大。最大允许 {MAX_FILE_SIZE // 1024 // 1024} MB。"
        )

    # 2. 校验文件类型
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file.content_type}。"
        )

    # 3. 保存文件到物理存储
    try:
        storage_path = await storage_service.save(file, sub_path="chat_attachments")
    except Exception as e:
        # 在这里捕获存储过程中的潜在异常
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件存储失败: {e}"
        )

    # 4. 在数据库中创建文件元数据记录，标记为临时文件
    db_file = await file_crud.create_file(
        db=db,
        filename=file.filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        size=file.size,
        management_type=FileManagementType.TEMPORARY.value
    )

    # 5. 构建并返回响应
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
async def download_file(storage_path: str):
    """
    根据文件的存储路径提供文件访问。
    注意：此端点目前是公开的。在生产环境中，应根据业务需求添加认证和授权。
    """
    # 当前实现仅支持本地存储服务
    if not isinstance(storage_service, LocalStorageService):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Download not implemented for the current storage service type."
        )

    # 安全性检查：确保请求的路径在预期的存储根目录内，防止路径遍历攻击
    base_path = storage_service.base_path.resolve()
    file_path = (base_path / storage_path).resolve()

    if not str(file_path).startswith(str(base_path)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to the requested file path is forbidden."
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    return FileResponse(path=file_path)

