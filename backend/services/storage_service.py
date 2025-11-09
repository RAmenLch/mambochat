# backend/services/storage_service.py

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
import aiofiles
import aiofiles.os  # 导入 aiofiles.os 模块
from fastapi import UploadFile

class AbstractStorageService(ABC):
    """
    文件存储服务的抽象基类，定义了标准的文件操作接口。
    """
    @abstractmethod
    async def save(self, file: UploadFile, sub_path: str) -> str:
        """
        保存上传的文件。

        :param file: FastAPI的UploadFile对象。
        :param sub_path: 文件存储的子目录，例如 'avatars'。
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


class LocalStorageService(AbstractStorageService):
    """
    使用本地文件系统实现的文件存储服务。
    """
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

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

    def get_url(self, storage_path: str) -> str:
        # 构建一个指向API下载端点的相对URL
        return f"/api/files/download/{storage_path}"

    async def delete(self, storage_path: str) -> None:
        if not storage_path:
            return

        file_path = self.base_path / storage_path

        try:
            await aiofiles.os.remove(file_path)
        except FileNotFoundError:
            # 如果文件已不存在，则静默处理，因为目标（文件被删除）已经达成。
            pass

# --- 服务实例化 ---

# 从环境变量中读取存储根路径，默认为 './uploads'
STORAGE_PATH = os.getenv("STORAGE_PATH", "./uploads")

# 创建LocalStorageService的单例
storage_service: AbstractStorageService = LocalStorageService(base_path=STORAGE_PATH)
