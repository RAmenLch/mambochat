"""
SillyTavern 角色卡导入插件。

将 SillyTavern PNG 角色卡拆解为 Resource 树（文件夹 + 多个 FILE 资源）。
对外暴露：
- is_sillytavern_png(data): 判断 PNG 是否为角色卡
- import_sillytavern_png(db, file, parent_id): 导入角色卡
"""

from .detection import is_sillytavern_card_png
from .service import SillyTavernImportError, SillyTavernImportService

__all__ = [
    "is_sillytavern_card_png",
    "SillyTavernImportService",
    "SillyTavernImportError",
]
