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
        pass

    @abstractmethod
    async def save_from_bytes(self, data: bytes, filename: str, sub_path: str) -> str:
        pass

    @abstractmethod
    def get_url(self, storage_path: str) -> str:
        pass

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        pass

    @abstractmethod
    async def read_bytes(self, storage_path: str) -> bytes:
        pass

    @abstractmethod
    async def edit(self, storage_path: str, new_content: bytes) -> None:
        """
        直接编辑/覆盖存储系统中的文件内容。
        """
        raise NotImplementedError("不支持此操作")


class LocalStorageService(AbstractStorageService):
    """
    使用本地文件系统实现的文件存储服务。
    """
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, storage_path: Union[str, Path]) -> Path:
        full_path = (self.base_path / storage_path).resolve()
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError("Attempted to access a path outside the storage directory.")
        return full_path

    async def save(self, file: UploadFile, sub_path: str) -> str:
        unique_filename = f"{uuid.uuid4()}"
        storage_dir = self.base_path / sub_path
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / unique_filename

        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)

        relative_path = Path(sub_path) / unique_filename
        return str(relative_path).replace('\\', '/')

    async def save_from_bytes(self, data: bytes, filename: str, sub_path: str) -> str:
        unique_filename = f"{uuid.uuid4()}"
        storage_dir = self.base_path / sub_path
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / unique_filename

        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(data)

        relative_path = Path(sub_path) / unique_filename
        return str(relative_path).replace('\\', '/')

    def get_url(self, storage_path: str) -> str:
        return f"/api/files/download/{storage_path}"

    async def delete(self, storage_path: str) -> None:
        if not storage_path:
            return

        try:
            file_path = self._get_full_path(storage_path)
            await aiofiles.os.remove(file_path)
        except (FileNotFoundError, ValueError):
            pass

    async def read_bytes(self, storage_path: str) -> bytes:
        if not storage_path:
            raise FileNotFoundError("Storage path cannot be empty.")

        try:
            file_path = self._get_full_path(storage_path)
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except (FileNotFoundError, ValueError) as e:
            raise FileNotFoundError(f"File not found at path: {storage_path}") from e

    async def edit(self, storage_path: str, new_content: bytes) -> None:
        raise NotImplementedError("本地文件系统不支持直接编辑，请使用替换逻辑")


# --- 服务实例化 ---

import os

from backend._cli_args import STORAGE_PATH as _CLI_STORAGE_PATH

_PROJECT_ROOT = Path(__file__).parent.parent
_default = str(_PROJECT_ROOT.joinpath("uploads"))
_ENV_STORAGE_PATH = os.getenv("MAMBO_DOCKER_STORAGE_PATH")
STORAGE_PATH_STR = _CLI_STORAGE_PATH or _ENV_STORAGE_PATH or _default
storage_service: AbstractStorageService = LocalStorageService(base_path=STORAGE_PATH_STR)
