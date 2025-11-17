# backend/services/storage_service.py

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
import aiofiles
import aiofiles.os
from fastapi import UploadFile
from typing import Union

class AbstractStorageService(ABC):
    """
    文件存储服务的抽象基类，定义了标准的文件操作接口。
    """
    @abstractmethod
    async def save(self, file: UploadFile, sub_path: str) -> str:
        """
        保存上传的文件。

        :param file: FastAPI的UploadFile对象。
        :param sub_path: 文件存储的子目录，例如 'chat_attachments'。
        :return: 文件在存储系统中的相对路径。
        """
        pass

    @abstractmethod
    async def save_from_bytes(self, data: bytes, filename: str, sub_path: str) -> str:
        """
        直接从二进制数据保存文件。

        :param data: 文件的二进制内容。
        :param filename: 用于提取文件扩展名的原始文件名。
        :param sub_path: 文件存储的子目录。
        :return: 文件在存储系统中的相对路径。
        """
        pass

    @abstractmethod
    def get_url(self, storage_path: str) -> str:
        """
        根据存储路径获取文件的可公开访问URL。

        :param storage_path: 文件在存储系统中的相对路径。
        :return: 文件的完整访问URL。
        """
        pass

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """
        根据存储路径删除文件。

        :param storage_path: 文件在存储系统中的相对路径。
        """
        pass

    @abstractmethod
    async def read_bytes(self, storage_path: str) -> bytes:
        """
        根据存储路径读取文件的二进制内容。

        :param storage_path: 文件在存储系统中的相对路径。
        :return: 文件的二进制内容。
        """
        pass


class LocalStorageService(AbstractStorageService):
    """
    使用本地文件系统实现的文件存储服务。
    """
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, storage_path: Union[str, Path]) -> Path:
        """内部辅助函数，安全地构建并返回文件的绝对路径。"""
        full_path = (self.base_path / storage_path).resolve()
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError("Attempted to access a path outside the storage directory.")
        return full_path

    async def save(self, file: UploadFile, sub_path: str) -> str:
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"

        storage_dir = self.base_path / sub_path
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / unique_filename

        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # 以1MB的块进行读写
                await out_file.write(content)

        relative_path = Path(sub_path) / unique_filename
        return str(relative_path).replace('\\', '/') # 保证路径分隔符的统一性

    async def save_from_bytes(self, data: bytes, filename: str, sub_path: str) -> str:
        file_extension = Path(filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"

        storage_dir = self.base_path / sub_path
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / unique_filename

        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(data)

        relative_path = Path(sub_path) / unique_filename
        return str(relative_path).replace('\\', '/')

    def get_url(self, storage_path: str) -> str:
        # 构建一个指向API下载端点的相对URL
        return f"/api/files/download/{storage_path}"

    async def delete(self, storage_path: str) -> None:
        if not storage_path:
            return

        try:
            file_path = self._get_full_path(storage_path)
            await aiofiles.os.remove(file_path)
        except (FileNotFoundError, ValueError):
            # 如果文件不存在或路径无效，则静默处理，因为目标（文件被删除）已经达成。
            pass

    async def read_bytes(self, storage_path: str) -> bytes:
        if not storage_path:
            raise FileNotFoundError("Storage path cannot be empty.")

        try:
            file_path = self._get_full_path(storage_path)
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except (FileNotFoundError, ValueError) as e:
            # 重新抛出FileNotFoundError以清晰地表明文件未找到
            raise FileNotFoundError(f"File not found at path: {storage_path}") from e


# --- 服务实例化 ---

# 从环境变量中读取存储根路径，默认为 './uploads'
STORAGE_PATH = os.getenv("STORAGE_PATH", "./uploads")

# 创建LocalStorageService的单例
storage_service: AbstractStorageService = LocalStorageService(base_path=STORAGE_PATH)
