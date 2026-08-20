# backend/services/resource_export_service.py
"""资源文件夹导出为 ZIP 的服务。

导出原则：
- 仅导出最新版本（Resource.latestVersionId 指向的活跃版本）。
- 产物为纯净的文件/文件夹树，剔除资源系统元数据（版本、attributes、
  kb_id、kb_config、向量、切片等派生数据）。
- file 资源导出原始字节，文本类资源导出文本内容，文件名一律使用资源名，
  不追加扩展名，也不使用 File 表的原始 filename。
"""

import io
import re
import zipfile
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import resource_crud
from backend.exceptions import AppHTTPException
from backend.models import resource_model
from backend.schemas.enums import ResourceType, ResourceItemType
from backend.services.file_service import FileService

_FILE_LIKE_TYPES = {ResourceType.FILE.value, ResourceType.KB_FILE.value}
_TEXT_LIKE_TYPES = {
    ResourceType.SYSTEM_PROMPT.value,
    ResourceType.SUBMESSAGE_TEMPLATE.value,
}
# 作为目录处理的类型
_DIR_ITEM_TYPE = ResourceItemType.FOLDER.value

_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _sanitize_name(name: str) -> str:
    """清洗资源名，剥离路径穿越与 zip 不友好字符。"""
    cleaned = _INVALID_NAME_CHARS.sub("_", name or "")
    cleaned = cleaned.strip().strip(".")
    return cleaned or "unnamed"


def _unique_name(base: str, used: set) -> str:
    """在同一目录下对重名追加 (2)/(3) 后缀去重。"""
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base} ({i})" in used:
        i += 1
    candidate = f"{base} ({i})"
    used.add(candidate)
    return candidate


class ResourceExporter:
    """将某个文件夹资源的整个子树打包为 ZIP。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    async def export_folder_zip(self, folder_id: str) -> tuple[bytes, str]:
        """导出指定文件夹为 zip 字节。返回 (zip_bytes, folder_name)。"""
        folder = await resource_crud.get_resource(self.db, folder_id)
        if not folder:
            raise AppHTTPException(status_code=404, error_code="RESOURCE_NOT_FOUND", detail="资源不存在")
        if folder.itemType != _DIR_ITEM_TYPE:
            raise AppHTTPException(
                status_code=400,
                error_code="RESOURCE_NOT_FOLDER",
                detail="仅文件夹类型的资源支持导出",
            )

        descendants = await resource_crud.get_descendants_with_versions(self.db, folder_id)
        children_map: Dict[Optional[str], List[resource_model.Resource]] = {}
        for res in descendants:
            children_map.setdefault(res.parentId, []).append(res)
        for siblings in children_map.values():
            siblings.sort(key=lambda r: (r.sortOrder or 0, r.name or ""))

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            await self._write_children(zf, folder_id, children_map, prefix="")
        buffer.seek(0)
        return buffer.read(), folder.name

    async def _write_children(
        self,
        zf: zipfile.ZipFile,
        parent_id: str,
        children_map: Dict[Optional[str], List[resource_model.Resource]],
        prefix: str,
    ) -> None:
        used_names: set = set()
        for node in children_map.get(parent_id, []):
            name = _unique_name(_sanitize_name(node.name), used_names)
            arcname = f"{prefix}{name}"

            if node.itemType == _DIR_ITEM_TYPE:
                # folder / knowledge_base / skill 统一按目录导出，递归子树。
                # knowledge_base 的切片/向量/kb_config 等派生数据不导出。
                zf.writestr(arcname + "/", "")
                await self._write_children(zf, node.id, children_map, prefix=arcname + "/")
                continue

            version = node.latest_version
            if version is None:
                # 无版本的内容节点导出为空文件，保证树结构完整。
                zf.writestr(arcname, b"")
                continue

            if node.resourceType in _FILE_LIKE_TYPES:
                data = await self._read_file_bytes(node, version)
            elif node.resourceType in _TEXT_LIKE_TYPES:
                data = (version.content or "").encode("utf-8")
            else:
                # 其他未知内容类型按文本内容兜底导出。
                data = (version.content or "").encode("utf-8")
            zf.writestr(arcname, data)

    async def _read_file_bytes(
        self,
        node: resource_model.Resource,
        version: resource_model.ResourceVersion,
    ) -> bytes:
        file_id = version.content
        if not file_id:
            return b""
        try:
            return await self.file_service.get_file_content(file_id)
        except Exception as exc:
            raise AppHTTPException(
                status_code=400,
                error_code="RESOURCE_EXPORT_CONTENT_MISSING",
                detail=f"资源 '{node.name}' 的文件内容缺失，无法导出: {exc}",
            )
