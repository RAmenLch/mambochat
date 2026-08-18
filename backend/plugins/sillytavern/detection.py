"""
SillyTavern 角色卡 PNG 轻量识别模块。

仅对 PNG 做"是否为 SillyTavern 角色卡"的判断，不做完整解析。
识别逻辑：扫描 PNG chunk，检查是否存在 chara / ccv3 的 tEXt 文本块。
标准库实现，零第三方依赖。
"""

import struct
from typing import Optional

# PNG 文件签名
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# SillyTavern 角色卡元数据块关键字（V2 / V3）
_CHARA_KEYWORD = "chara"
_CCV3_KEYWORD = "ccv3"


def is_png(data: bytes) -> bool:
    """判断字节流是否为有效的 PNG 文件。"""
    return isinstance(data, (bytes, bytearray)) and data[:8] == _PNG_SIGNATURE


def _iter_png_chunks(data: bytes):
    """
    遍历 PNG 的 chunk 序列，yield (chunk_type, chunk_data)。
    PNG chunk 结构: [4 字节长度][4 字节类型][数据][4 字节 CRC]
    """
    offset = 8  # 跳过 8 字节签名
    length = len(data)
    while offset + 8 <= length:
        (chunk_len,) = struct.unpack(">I", data[offset:offset + 4])
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + chunk_len]
        yield chunk_type, chunk_data
        # 移动到下一个 chunk（长度 4 + 类型 4 + 数据 + CRC 4）
        offset += 12 + chunk_len


def find_card_text_chunk(data: bytes) -> Optional[str]:
    """
    在 PNG 中查找角色卡 tEXt 块，返回 (keyword, text)。

    优先返回 ccv3（V3），回退到 chara（V2）。
    tEXt 块数据格式: [关键字]\x00[文本]，文本为 base64 编码的 JSON。
    找不到则返回 None。
    """
    if not is_png(data):
        return None

    text_chunks = []
    for chunk_type, chunk_data in _iter_png_chunks(data):
        if chunk_type != b"tEXt":
            continue
        # tEXt 数据: keyword\0text
        sep = chunk_data.find(b"\x00")
        if sep < 0:
            continue
        keyword = chunk_data[:sep].decode("latin-1", errors="ignore").strip().lower()
        text = chunk_data[sep + 1:].decode("latin-1", errors="ignore")
        text_chunks.append((keyword, text))

    if not text_chunks:
        return None

    # 优先 ccv3
    for keyword, text in text_chunks:
        if keyword == _CCV3_KEYWORD:
            return text
    # 回退 chara
    for keyword, text in text_chunks:
        if keyword == _CHARA_KEYWORD:
            return text

    return None


def is_sillytavern_card_png(data: bytes) -> bool:
    """判断一个 PNG 是否为 SillyTavern 角色卡（含 chara/ccv3 元数据块）。"""
    return find_card_text_chunk(data) is not None
