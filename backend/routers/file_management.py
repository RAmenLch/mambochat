# backend/routers/file_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ..services.storage_service import storage_service, LocalStorageService

router = APIRouter(
    prefix="/api/files",
    tags=["File Management"]
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

