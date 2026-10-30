"""生图 / 展示共用的「落盘 → 落库」逻辑。

「把工作区里的一个文件（或一组刚下载好的图片字节）变成文件库记录」这件事，
在 ``show`` 工具与 ``image_generate_show`` 工具里完全一致，集中在本模块实现，
避免两处各写一份 mime 嗅探与 ``FileService`` 调用。
"""

import logging
from pathlib import PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from mambo_agents.backends.protocol import BackendProtocol, _get_mime_type
from mambo_agents.backends.schemas import VirtualPath

from backend.schemas.enums import FileManagementType
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Any]

# 常见图片格式的文件头（用于校正兜底扩展名带来的 mime 偏差）
_IMAGE_MAGIC: Tuple[Tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


async def read_workspace_file(
    backend: BackendProtocol, path: str
) -> Tuple[Optional[bytes], Optional[str]]:
    """从 backend 读取文件字节，返回 ``(内容, 错误描述)``。

    使用 ``adownload_files``（异步协议方法），让带实例锁的 backend
    （如 ``SshBackend._async_lock``）可以串行化 SFTP 访问。
    """
    try:
        results = await backend.adownload_files([VirtualPath(path)])
        if not results:
            return None, "adownload_files returned empty results"
        result = results[0]
        if result.error:
            return None, str(result.error)
        return result.content, None
    except Exception as exc:  # noqa: BLE001 - 读文件失败统一转文本
        return None, str(exc)


def _sniff_image_mime(data: Optional[bytes]) -> Optional[str]:
    """按文件头识别常见图片格式（异步生图的扩展名是兜底的，需以内容为准）。"""
    if not data or len(data) < 12:
        return None
    head = data[:16]
    for magic, mime in _IMAGE_MAGIC:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def resolve_mime(filename: str, mime: Optional[str], data: Optional[bytes]) -> str:
    """确定文件 mime。

    优先信任调用方给出的 mime（生图 blob 自带，准确）；若该 mime 是图片类型，
    则用文件头校正一次（异步生图按 ``.png`` 兜底命名时实际可能是 jpeg）；
    内容是可解码 UTF-8 文本时再让 ``FileUtils`` 重新判定（覆盖 ``.env`` /
    ``Dockerfile`` 这类扩展名不可靠的纯文本文件）。
    """
    resolved = mime or _get_mime_type(filename)
    if not data:
        return resolved

    if resolved.startswith("image/"):
        return _sniff_image_mime(data) or resolved

    try:
        data[:8192].decode("utf-8")
    except (UnicodeDecodeError, ValueError, LookupError):
        return resolved

    from backend.utils.file_utils import FileUtils

    return FileUtils.correct_mime_type(filename, resolved, data[:8192])


async def persist_bytes(
    session_factory: SessionFactory,
    *,
    data: bytes,
    filename: str,
    mime: Optional[str],
) -> str:
    """把字节写入文件库，返回 ``file_id``；失败时抛原始异常。"""
    final_mime = resolve_mime(filename, mime, data)
    async with session_factory() as db:
        service = FileService(db)
        db_file = await service.save_file_from_bytes(
            data=data or b"",
            filename=filename,
            mime_type=final_mime,
            management_type=[FileManagementType.SUB_MESSAGE.value],
            sub_path="chat_attachments",
        )
    return db_file.id


async def persist_path(
    backend: BackendProtocol,
    session_factory: SessionFactory,
    path: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """读取工作区文件并入库，返回 ``(元信息, 错误描述)``。"""
    content, error = await read_workspace_file(backend, path)
    if error:
        return None, error

    filename = PurePosixPath(path).name
    mime = _get_mime_type(path)
    try:
        file_id = await persist_bytes(
            session_factory, data=content or b"", filename=filename, mime=mime
        )
    except HTTPException as exc:
        return None, str(exc.detail)
    except Exception as exc:  # noqa: BLE001 - 入库失败统一转文本
        return None, str(exc)

    return {
        "file_id": file_id,
        "filename": filename,
        "mime_type": resolve_mime(filename, mime, content),
    }, None


def collect_file_ids(payload: Any) -> List[str]:
    """从工具结果里收集待展示的 file_id（兼容单文件与多文件两种形态）。

    ``show`` 返回 ``{"file_id": ...}``；``image_generate_show`` 返回
    ``{"files": [{"file_id": ..., "path": ...}, ...]}``。
    """
    if not isinstance(payload, dict):
        return []

    file_id = payload.get("file_id")
    if isinstance(file_id, str) and file_id:
        return [file_id]

    files = payload.get("files")
    if not isinstance(files, list):
        return []
    return [
        item["file_id"]
        for item in files
        if isinstance(item, dict)
        and isinstance(item.get("file_id"), str)
        and item["file_id"]
    ]


async def persist_uploaded(
    session_factory: SessionFactory,
    items: Iterable[Tuple[Any, bytes]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """把已落盘的图片字节逐张入库，返回 ``(成功列表, 错误列表)``。

    ``items`` 的元素是 ``(ImageTarget, data)``；单张失败不影响其余图片。
    """
    files: List[Dict[str, Any]] = []
    errors: List[str] = []
    for target, data in items:
        filename = PurePosixPath(target.path.value).name
        try:
            file_id = await persist_bytes(
                session_factory, data=data, filename=filename, mime=target.mime_type
            )
        except HTTPException as exc:
            errors.append(f"{target.path.value}: {exc.detail}")
            continue
        except Exception as exc:  # noqa: BLE001 - 单张失败不影响其余图片
            logger.warning("persist image %s failed: %s", target.path.value, exc)
            errors.append(f"{target.path.value}: {exc}")
            continue
        files.append(
            {
                "index": target.index,
                "path": target.path.value,
                "mime": target.mime_type,
                "file_id": file_id,
            }
        )
    return files, errors


__all__ = [
    "read_workspace_file",
    "resolve_mime",
    "persist_bytes",
    "persist_path",
    "persist_uploaded",
    "collect_file_ids",
]
