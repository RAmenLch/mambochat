"""
SillyTavern 角色卡数据模型与字段提取。

对齐 SillyTavern 的 V2/V3 规范：
- 人物字段（description / personality / scenario / first_mes / mes_example 等）
- 世界书（character_book）
- RisuAI 立绘/表情（data.extensions.risuai）
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RisuImage:
    """RisuAI 内嵌图片（立绘/表情）。"""
    label: str
    base64_data: str


@dataclass
class ExtractedCard:
    """从角色卡中提取的可拆分数据。"""
    spec: Optional[str]                      # chara_card_v1 / v2 / v3 / None
    spec_version: Optional[str]
    name: str
    data: Dict[str, Any]                     # V2/V3 的 data 对象；V1 直接是扁平字段
    full_card: Dict[str, Any]                # 原始完整卡 JSON
    character_book: Optional[Dict[str, Any]] = None
    risu_images: List[RisuImage] = field(default_factory=list)

    # --- 人物字段（从 data 中提取）---
    @property
    def description(self) -> str:
        return str(self.data.get("description") or "")

    @property
    def personality(self) -> str:
        return str(self.data.get("personality") or "")

    @property
    def scenario(self) -> str:
        return str(self.data.get("scenario") or "")

    @property
    def first_mes(self) -> str:
        return str(self.data.get("first_mes") or "")

    @property
    def mes_example(self) -> str:
        return str(self.data.get("mes_example") or "")

    @property
    def creator_notes(self) -> str:
        return str(self.data.get("creator_notes") or "")

    @property
    def system_prompt(self) -> str:
        return str(self.data.get("system_prompt") or "")

    @property
    def post_history_instructions(self) -> str:
        return str(self.data.get("post_history_instructions") or "")

    @property
    def tags(self) -> List[str]:
        raw = self.data.get("tags")
        if isinstance(raw, list):
            return [str(t) for t in raw if str(t).strip()]
        return []


def _get_data(card: Dict[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """
    返回 (spec, spec_version, data)。
    - V2/V3: data 在 card.data 下
    - V1: data 就是 card 本身（扁平）
    """
    spec = card.get("spec")
    spec_version = card.get("spec_version")

    if spec == "chara_card_v2":
        data = card.get("data") or {}
        return "chara_card_v2", str(spec_version or "2.0"), data
    if spec == "chara_card_v3":
        data = card.get("data") or {}
        return "chara_card_v3", str(spec_version or "3.0"), data
    # V1 或其他：扁平结构，data 即 card
    return None, spec_version, card


def _extract_character_book(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    book = data.get("character_book")
    if isinstance(book, dict) and book:
        return book
    return None


def _extract_risu_images(data: Dict[str, Any]) -> List[RisuImage]:
    """从 data.extensions.risuai 提取立绘/表情（additionalAssets + emotions）。"""
    images: List[RisuImage] = []
    risu = (data.get("extensions") or {}).get("risuai")
    if not isinstance(risu, dict):
        return images

    for key in ("additionalAssets", "emotions"):
        entries = risu.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            label, base64_data = entry
            if not base64_data:
                continue
            images.append(RisuImage(label=str(label), base64_data=str(base64_data)))

    return images


def _strip_risu_images_from_card(card: Dict[str, Any]) -> None:
    """
    对齐 SillyTavern：从卡 JSON 中删除 additionalAssets/emotions（立绘已提取为独立文件）。
    保留 risuai.source 用于溯源。
    """
    try:
        risu = card["data"]["extensions"]["risuai"]
    except (KeyError, TypeError):
        return
    if isinstance(risu, dict):
        risu.pop("additionalAssets", None)
        risu.pop("emotions", None)


def extract_card(card: Dict[str, Any]) -> ExtractedCard:
    """
    从原始卡 JSON 提取可拆分数据。

    副作用：若存在 risuai，会就地删除卡中的 additionalAssets/emotions（对齐 SillyTavern）。
    """
    spec, spec_version, data = _get_data(card)
    name = str(data.get("name") or card.get("name") or "untitled")

    # 立绘在删除前先提取
    risu_images = _extract_risu_images(data)
    # 删除卡 JSON 中的立绘 base64
    _strip_risu_images_from_card(card)

    character_book = _extract_character_book(data)

    return ExtractedCard(
        spec=spec,
        spec_version=spec_version,
        name=name,
        data=data,
        full_card=card,
        character_book=character_book,
        risu_images=risu_images,
    )
