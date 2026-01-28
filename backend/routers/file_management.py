# backend/routers/file_management.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.storage_service import storage_service, LocalStorageService
from backend.database import get_db
from backend.crud import file_crud
from backend import schemas
from backend.schemas.enums import FileManagementType

router = APIRouter(
    prefix="/api/files",
    tags=["File Management"]
)

# 定义允许上传的文件类型和最大大小
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# 扩展后的文件MIME类型白名单
ALLOWED_MIME_TYPES = {
    # --- 文本与标记语言 (Text & Markup) ---
    "text/plain",          # .txt, .log
    "text/markdown",       # .md
    "text/csv",            # .csv
    "text/html",           # .html
    "text/css",            # .css
    "application/rtf",     # .rtf (富文本)

    # --- 图片 (Images) ---
    "image/jpeg",          # .jpeg, .jpg
    "image/png",           # .png
    "image/gif",           # .gif
    "image/webp",          # .webp
    "image/svg+xml",       # .svg (矢量图)
    "image/bmp",           # .bmp
    "image/tiff",          # .tiff, .tif
    "image/heic",          # .heic (苹果高效图片格式)
    "image/heif",          # .heif (苹果高效图片格式)

    # --- 代码与数据 (Code & Data) ---
    "application/json",    # .json
    "application/xml",     # .xml (更通用)
    "text/xml",            # .xml (作为文本)
    "application/x-yaml",  # .yaml, .yml
    "text/yaml",           # .yaml, .yml (备用)
    "text/x-python",       # .py
    "application/javascript", # .js
    "text/typescript",     # .ts
    "text/x-java-source",  # .java
    "text/x-csharp",       # .cs
    "text/x-c",            # .c
    "text/x-c++src",       # .cpp
    "text/x-go",           # .go
    "text/x-ruby",         # .rb
    "application/sql",     # .sql
    "application/x-sh",    # .sh (Shell脚本)
    "application/x-ipynb+json", # .ipynb (Jupyter Notebook)

    # --- 音频 (Audio) ---
    "audio/mpeg",          # .mp3
    "audio/wav",           # .wav
    "audio/ogg",           # .ogg
    "audio/webm",          # .webm (音频)
    "audio/mp4",           # .m4a
    "audio/flac",          # .flac (无损音频)
    "audio/aac",           # .aac

    # --- 视频 (Video) ---
    "video/mp4",           # .mp4
    "video/webm",          # .webm (视频)
    "video/quicktime",     # .mov (Apple QuickTime)
    "video/x-msvideo",     # .avi
    "video/x-matroska",    # .mkv

    # --- 文档类型 (保留) ---
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # .xlsx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
}


async def correct_mime_type(file: UploadFile) -> str:
    """
    修正文件的 MIME 类型。
    主要处理以下情况：
    1. .sql 文件常被识别为 application/octet-stream，需修正为 application/sql。
    2. .ts 文件既可能是 TypeScript 也可能是 MPEG 视频流，需通过嗅探文件头区分。
    """
    original_content_type = file.content_type or "application/octet-stream"
    filename = file.filename.lower() if file.filename else ""

    # 修正 SQL 文件类型
    if original_content_type == "application/octet-stream" and filename.endswith(".sql"):
        return "application/sql"

    # 修正 .ts 文件类型
    if filename.endswith(".ts"):
        # 读取文件前 1KB 数据进行嗅探
        chunk = await file.read(1024)
        await file.seek(0)  # 重置文件指针，确保后续保存文件完整

        # 检查是否包含空字节 (二进制文件通常包含 0x00)
        if b'\x00' in chunk:
            return original_content_type

        # 尝试 UTF-8 解码，成功则认为是文本代码
        try:
            chunk.decode('utf-8')
            return "text/typescript"
        except UnicodeDecodeError:
            return original_content_type

    return original_content_type


@router.post(
    "/upload",
    response_model=schemas.File,
    summary="上传临时文件"
)
async def upload_temporary_file(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大。最大允许 {MAX_FILE_SIZE // 1024 // 1024} MB。"
        )

    # 获取修正后的 MIME 类型
    final_mime_type = await correct_mime_type(file)

    if final_mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {final_mime_type}。"
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
        mime_type=final_mime_type,  # 存入数据库的是修正后的类型
        size=file.size,
        management_type=[FileManagementType.TEMPORARY.value]
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
    # 1. 使用 CRUD 函数通过 storage_path 获取文件元数据
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