"""
SillyTavern 角色卡解析/拆分逻辑测试。

生成一个带 chara tEXt 块的 PNG，验证 detection / parse / split。
"""
import base64
import json
import struct
import zlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.plugins.sillytavern.detection import is_sillytavern_card_png, is_png
from backend.plugins.sillytavern.parser import parse_card
from backend.plugins.sillytavern.models import extract_card
from backend.plugins.sillytavern.splitter import split_card


def make_png_with_text(text_chunks):
    """构造一个最小 PNG，带指定 tEXt 块。"""
    def chunk(ctype, cdata):
        return (struct.pack(">I", len(cdata)) + ctype + cdata
                + struct.pack(">I", zlib.crc32(ctype + cdata) & 0xFFFFFFFF))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    # 一个 1x1 像素的 IDAT
    raw = zlib.compress(b"\x00\x00\x00\x00\x00")
    idat = chunk(b"IDAT", raw)
    iend = chunk(b"IEND", b"")
    out = sig + ihdr
    for keyword, text in text_chunks:
        out += chunk(b"tEXt", keyword.encode() + b"\x00" + text.encode())
    out += idat + iend
    return out


def make_card():
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "测试角色",
            "description": "这是一个测试角色。",
            "personality": "友好、聪明",
            "scenario": "在一座魔法图书馆中。",
            "first_mes": "你好，我是图书管理员。",
            "mes_example": "<START>\n{{user}}: 你好\n{{char}}: 欢迎光临",
            "creator_notes": "测试用角色",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": ["测试", "图书馆"],
            "creator": "tester",
            "character_version": "1.0",
            "extensions": {
                "talkativeness": 0.5,
                "risuai": {
                    "source": ["risurealm:123"],
                    "additionalAssets": [["default", base64.b64encode(b"\x89PNG\x0d\x0a\x1a\x0aIMG1").decode()]],
                    "emotions": [["joy", base64.b64encode(b"\x89PNG\x0d\x0a\x1a\x0aIMG2").decode()]],
                },
            },
            "character_book": {
                "name": "魔法世界",
                "entries": [
                    {"keys": ["图书馆"], "content": "图书馆的规则", "id": 0, "enabled": True,
                     "insertion_order": 10, "extensions": {}},
                    {"keys": ["魔法"], "content": "魔法设定", "id": 1, "enabled": True,
                     "insertion_order": 20, "extensions": {}},
                ],
            },
        },
    }
    return card


def main():
    card = make_card()
    card_json = json.dumps(card)
    b64 = base64.b64encode(card_json.encode("utf-8")).decode("ascii")
    png = make_png_with_text([("chara", b64)])

    # 1. detection
    assert is_png(png), "is_png failed"
    assert is_sillytavern_card_png(png), "is_sillytavern_card_png failed"
    # 普通 PNG（无角色卡元数据）不应被识别
    plain_png = make_png_with_text([("Comment", "nothing")])
    assert not is_sillytavern_card_png(plain_png), "plain png should not be a card"
    print("[OK] detection")

    # 2. parse
    parsed = parse_card(png)
    assert parsed.card["spec"] == "chara_card_v2", "spec mismatch"
    assert parsed.avatar_bytes[:8] == b"\x89PNG\r\n\x1a\n", "avatar should be png"
    assert b"chara" not in parsed.avatar_bytes, "avatar should not contain metadata"
    print("[OK] parse")

    # 3. extract + split
    extracted = extract_card(parsed.card)
    assert extracted.name == "测试角色", f"name={extracted.name}"
    assert extracted.character_book is not None, "world book missing"
    assert len(extracted.risu_images) == 2, f"risu images={len(extracted.risu_images)}"
    # risuai base64 已从卡中删除
    assert "additionalAssets" not in extracted.full_card["data"]["extensions"]["risuai"], "risu base64 not removed"
    print("[OK] extract")

    split = split_card(extracted, parsed.avatar_bytes)
    rel_paths = [f.rel_path for f in split.files]
    print("[OK] split files:", rel_paths)
    assert "character_card.json" in rel_paths
    assert "character.md" in rel_paths
    assert "world_book.json" in rel_paths
    assert "avatar.png" in rel_paths
    assert "sprites/default.png" in rel_paths
    assert "sprites/joy.png" in rel_paths

    # 4. json 多行（grep 可用）
    wb = next(f for f in split.files if f.rel_path == "world_book.json")
    wb_text = wb.data.decode("utf-8")
    assert '"content": "图书馆的规则"' in wb_text, "world_book not multiline/greppable"
    assert '\n' in wb_text, "world_book should be multiline"
    print("[OK] world_book multiline greppable")

    # 5. character.md 含 tags，不含立绘清单
    md = next(f for f in split.files if f.rel_path == "character.md").data.decode("utf-8")
    assert "测试" in md and "图书馆" in md, "tags missing in md"
    assert "sprites" not in md and "risuai" not in md, "md should not contain sprite list"
    print("[OK] character.md")

    print("\n全部测试通过 ✅")


if __name__ == "__main__":
    main()
