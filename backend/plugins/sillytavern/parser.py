"""
SillyTavern 角色卡 PNG 完整解析模块。

从 PNG 的 tEXt 块读取角色卡 JSON（优先 ccv3，回退 chara），
并剥离元数据后返回纯头像图像字节。
标准库实现，零第三方依赖。
"""

import base64
import json
import struct
from dataclasses import dataclass
from typing import Optional

from .detection import _iter_png_chunks, is_png

# PNG chunk 类型
_CHUNK_TEXt = b"tEXt"
_CHUNK_IDAT = b"IDAT"
_CHUNK_IEND = b"IEND"

_CHARA_KEYWORD = "chara"
_CCV3_KEYWORD = "ccv3"


class SillyTavernCardError(Exception):
    """SillyTavern 角色卡解析错误。"""


@dataclass
class ParsedCard:
    """解析结果：角色卡 JSON + 纯头像字节。"""
    card: dict
    avatar_bytes: bytes


def _decode_text_chunk(chunk_data: bytes) -> Optional[tuple]:
    """解析单个 tEXt 块，返回 (keyword, base64_text)。"""
    sep = chunk_data.find(b"\x00")
    if sep < 0:
        return None
    keyword = chunk_data[:sep].decode("latin-1", errors="ignore").strip().lower()
    text = chunk_data[sep + 1:].decode("latin-1", errors="ignore")
    return keyword, text


def _collect_card_text(data: bytes) -> Optional[str]:
    """收集 tEXt 块中的角色卡 base64 文本（优先 ccv3，回退 chara）。"""
    ccv3_text = None
    chara_text = None
    for chunk_type, chunk_data in _iter_png_chunks(data):
        if chunk_type != _CHUNK_TEXt:
            continue
        parsed = _decode_text_chunk(chunk_data)
        if parsed is None:
            continue
        keyword, text = parsed
        if keyword == _CCV3_KEYWORD and ccv3_text is None:
            ccv3_text = text
        elif keyword == _CHARA_KEYWORD and chara_text is None:
            chara_text = text
    return ccv3_text or chara_text


def _strip_card_metadata(data: bytes) -> bytes:
    """
    移除 PNG 中所有 chara/ccv3 的 tEXt 块，返回仅含图像数据的 PNG。
    """
    chunks = list(_iter_png_chunks(data))
    kept = []
    for chunk_type, chunk_data in chunks:
        if chunk_type == _CHUNK_TEXt:
            parsed = _decode_text_chunk(chunk_data)
            if parsed is not None and parsed[0] in (_CHARA_KEYWORD, _CCV3_KEYWORD):
                continue  # 剔除角色卡元数据块
        kept.append((chunk_type, chunk_data))

    # 重写 PNG：签名 + 各 chunk（含正确的 CRC）
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    for chunk_type, chunk_data in kept:
        out += struct.pack(">I", len(chunk_data))
        out += chunk_type
        out += chunk_data
        crc = _crc32(chunk_type + chunk_data)
        out += struct.pack(">I", crc)
    return bytes(out)


def _crc32(data: bytes) -> int:
    """计算 PNG chunk 的 CRC32（多项式 0xEDB88320，初值 0，无取反差异已由 zlib 处理）。"""
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_card(data: bytes) -> ParsedCard:
    """
    解析 SillyTavern 角色卡 PNG。

    Args:
        data: PNG 文件字节。

    Returns:
        ParsedCard：包含 card (dict) 和 avatar_bytes (纯头像 PNG 字节)。

    Raises:
        SillyTavernCardError: 非 PNG、无元数据块、或 JSON 解析失败。
    """
    if not is_png(data):
        raise SillyTavernCardError("不是有效的 PNG 文件")

    card_text = _collect_card_text(data)
    if card_text is None:
        raise SillyTavernCardError("PNG 中未找到角色卡元数据块 (chara/ccv3)")

    try:
        card_json = base64.b64decode(card_text)
    except Exception as e:
        raise SillyTavernCardError(f"角色卡 base64 解码失败: {e}")

    try:
        card = json.loads(card_json.decode("utf-8"))
    except Exception as e:
        raise SillyTavernCardError(f"角色卡 JSON 解析失败: {e}")

    if not isinstance(card, dict):
        raise SillyTavernCardError("角色卡 JSON 不是对象")

    avatar_bytes = _strip_card_metadata(data)

    return ParsedCard(card=card, avatar_bytes=avatar_bytes)
