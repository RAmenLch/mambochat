"""
SillyTavern 角色卡拆分模块。

将提取后的角色卡拆解为一组可读文件（纯逻辑，不涉及 DB）：
- character_card.json  完整原始卡 JSON（多行格式化）
- character.md         角色设定（可读核心文字，含 tags）
- world_book.json      世界书（如有，多行格式化，entries 不压成一行）
- avatar.png           纯头像
- sprites/             RisuAI 立绘/表情（如有，子文件夹）
"""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .models import ExtractedCard, RisuImage


@dataclass
class SplitFile:
    """拆解出的单个文件。rel_path 为相对角色文件夹的路径（含子目录）。"""
    rel_path: str            # 例如 "sprites/joy.png"
    filename: str            # 例如 "joy.png"
    data: bytes
    mime_type: str


@dataclass
class SplitResult:
    """拆分结果。"""
    folder_name: str         # 角色文件夹名
    files: List[SplitFile] = field(default_factory=list)


def _json_bytes(obj) -> bytes:
    """
    将对象序列化为多行格式 JSON。
    indent=2、ensure_ascii=False，保证 entries 等不压成一行，grep 可命中。
    """
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    return text.encode("utf-8")


def _safe_filename(name: str, fallback: str = "file") -> str:
    """清理非法文件名字符。"""
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", str(name)).strip()
    return cleaned or fallback


def _build_character_md(card: ExtractedCard) -> str:
    """构建角色设定 Markdown（可读核心文字，含 tags，不含立绘清单）。"""
    lines = []
    lines.append(f"# {card.name}")
    lines.append("")

    if card.description:
        lines.append("## 描述 (Description)")
        lines.append(card.description)
        lines.append("")

    if card.personality:
        lines.append("## 性格 (Personality)")
        lines.append(card.personality)
        lines.append("")

    if card.scenario:
        lines.append("## 场景 (Scenario)")
        lines.append(card.scenario)
        lines.append("")

    if card.first_mes:
        lines.append("## 开场白 (First Message)")
        lines.append(card.first_mes)
        lines.append("")

    if card.mes_example:
        lines.append("## 对话示例 (Example Messages)")
        lines.append(card.mes_example)
        lines.append("")

    if card.creator_notes:
        lines.append("## 作者备注 (Creator Notes)")
        lines.append(card.creator_notes)
        lines.append("")

    if card.tags:
        lines.append("## 标签 (Tags)")
        lines.append(", ".join(card.tags))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def split_card(card: ExtractedCard, avatar_bytes: bytes) -> SplitResult:
    """
    将提取后的角色卡拆解为文件树。

    Args:
        card: 已提取的角色卡数据。
        avatar_bytes: 纯头像 PNG 字节。

    Returns:
        SplitResult：包含角色文件夹名和文件清单。
    """
    folder_name = _safe_filename(card.name, fallback="character")
    files: List[SplitFile] = []

    # 1. 完整原始卡 JSON（多行格式化，已剔除立绘 base64）
    files.append(SplitFile(
        rel_path="character_card.json",
        filename="character_card.json",
        data=_json_bytes(card.full_card),
        mime_type="application/json",
    ))

    # 2. 角色设定 md
    files.append(SplitFile(
        rel_path="character.md",
        filename="character.md",
        data=_build_character_md(card).encode("utf-8"),
        mime_type="text/markdown",
    ))

    # 3. 世界书（如有）
    if card.character_book is not None:
        files.append(SplitFile(
            rel_path="world_book.json",
            filename="world_book.json",
            data=_json_bytes(card.character_book),
            mime_type="application/json",
        ))

    # 4. 头像
    files.append(SplitFile(
        rel_path="avatar.png",
        filename="avatar.png",
        data=avatar_bytes,
        mime_type="image/png",
    ))

    # 5. RisuAI 立绘/表情（子文件夹 sprites/，对齐 SillyTavern 提取）
    seen_labels = set()
    for img in card.risu_images:
        safe_label = _safe_filename(img.label, fallback="sprite")
        # 对齐 SillyTavern：同名跳过不覆盖
        if safe_label in seen_labels:
            continue
        seen_labels.add(safe_label)
        try:
            img_bytes = base64.b64decode(img.base64_data)
        except Exception:
            continue
        filename = f"{safe_label}.png"
        files.append(SplitFile(
            rel_path=f"sprites/{filename}",
            filename=filename,
            data=img_bytes,
            mime_type="image/png",
        ))

    return SplitResult(folder_name=folder_name, files=files)
