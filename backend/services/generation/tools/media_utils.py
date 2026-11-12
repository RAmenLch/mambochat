# backend/services/generation/tools/media_utils.py
"""工具结果多模态媒体（read 读取的图片/音视频/文档）的落盘与展示文案。

主代理（``MamboAgentBuiltinToolProvider`` 的 MCP_TOOL 结果）与子代理步骤
（``SubAgentEventHandler`` 的 TaskSubStep 结果）共用这一套实现，保证：
- 媒体块统一经 ``SaveAndPersistFile`` 落库为平台 File，content 里只留 ``media`` 引用；
- 文件名统一从工具参数 ``file_path`` / ``path`` 派生（支持字符串、``{"value": ...}``
  与 ``VirtualPath`` 这类带 ``value`` 字段的对象）；
- 纯多模态结果的展示文案统一为「读取到图片 xxx.png（1.2 MB）」。
"""

import mimetypes
from typing import Any, Dict, List, Optional, Tuple

from backend.models.base_model import generate_uuid
from backend.schemas.message import MultimodalMedia
from backend.services.generation.core.instructions import SaveAndPersistFile

#: 媒体块 file_type → 允许的文件扩展名
MEDIA_EXTENSIONS: Dict[str, frozenset] = {
    "image": frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif"}),
    "audio": frozenset({".wav", ".mp3", ".aiff", ".aac", ".ogg", ".flac"}),
    "video": frozenset({".mp4", ".mpeg", ".mov", ".avi", ".flv", ".webm", ".wmv"}),
    "file": frozenset({".pdf", ".ppt", ".pptx"}),
}

_DEFAULT_EXTENSIONS = {"image": ".png", "audio": ".mp3", "video": ".mp4"}


def pick_media_path(value: Any) -> str:
    """取工具目标路径末段。

    支持四种入参形态：字符串路径（含 Windows 反斜杠）、工具参数字典
    （依次取 ``file_path`` / ``path``）、``{"value": ...}`` 字典，以及
    ``VirtualPath`` 这类带 ``value`` 字段的对象（read 结果的 ``read_file_path``）。
    无法解析时返回空串。
    """
    raw = value
    if isinstance(raw, dict):
        for key in ("file_path", "path", "value"):
            candidate = raw.get(key)
            if isinstance(candidate, str) and candidate.strip():
                raw = candidate
                break
        else:
            return ""
    elif not isinstance(raw, str):
        raw = getattr(raw, "value", None)
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return raw.replace("\\", "/").rstrip("/").split("/")[-1]


def make_media_filename(path_value: Any, file_type: str, mime_type: str, idx: int) -> str:
    """由工具目标路径派生可读文件名，并保证扩展名合法。"""
    name = pick_media_path(path_value)
    if not name:
        name = f"tool_{file_type}{mimetypes.guess_extension(mime_type) or ''}"

    allowed = MEDIA_EXTENSIONS.get(file_type, frozenset())
    lower = name.lower()
    if allowed and not any(lower.endswith(ext) for ext in allowed):
        name = f"{name}{_DEFAULT_EXTENSIONS.get(file_type, '.bin')}"

    if idx > 0:
        if "." in name:
            stem, ext = name.rsplit(".", 1)
            name = f"{stem}_{idx}.{ext}"
        else:
            name = f"{name}_{idx}"
    return name


def build_media_summary(media_refs: List[MultimodalMedia]) -> str:
    """为多模态工具结果生成人类可读摘要（供气泡/弹窗展示）。"""
    labels = {"image": "图片", "audio": "音频", "video": "视频", "file": "文档"}
    parts = []
    for ref in media_refs:
        label = labels.get(ref.file_type, "文件")
        size = ref.size_bytes or 0
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        elif size:
            size_str = f"{size} B"
        else:
            size_str = ""
        filename = ref.filename or ""
        parts.append(f"{label}{' ' + filename if filename else ''}{' (' + size_str + ')' if size_str else ''}")
    return "读取到" + "、".join(parts)


def persist_media_blocks(
    media_blocks: Optional[List[Dict[str, Any]]],
    path_value: Any = None,
) -> Tuple[List[MultimodalMedia], List[SaveAndPersistFile]]:
    """把工具结果媒体块落盘，返回（media 引用, 保存指令）。

    保存指令由调用方按原顺序 yield / 执行，确保 File 记录先于引用它的子消息写入。
    """
    media_refs: List[MultimodalMedia] = []
    save_instructions: List[SaveAndPersistFile] = []
    for idx, blk in enumerate(media_blocks or []):
        if not isinstance(blk, dict) or not blk.get("base64"):
            continue
        base64_data = str(blk["base64"])
        file_type = str(blk.get("type") or "file")
        mime_type = str(blk.get("mime_type") or "application/octet-stream")
        filename = make_media_filename(path_value, file_type, mime_type, idx)
        file_id = generate_uuid()
        save_instructions.append(SaveAndPersistFile(
            file_id=file_id,
            filename=filename,
            base64_data=base64_data,
            mime_type=mime_type,
        ))
        media_refs.append(MultimodalMedia(
            file_type=file_type,
            mime_type=mime_type,
            file_id=file_id,
            filename=filename,
            size_bytes=int(len(base64_data) * 3 / 4),
        ))
    return media_refs, save_instructions
