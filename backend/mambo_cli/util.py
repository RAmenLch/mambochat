"""通用小工具。"""
from __future__ import annotations

import argparse
import os


class UsageError(Exception):
    """参数用法/校验错误：main() 捕获后以退出码 2 退出（区别于 API 错误的 1）。"""

_MIME_MAP = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "text/xml",
    ".csv": "text/csv",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def guess_mime(filename: str) -> str:
    return _MIME_MAP.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")


def parse_bool(text: str) -> bool:
    """解析布尔值参数，失败抛出 argparse.ArgumentTypeError。"""
    lowered = text.strip().lower()
    if lowered in ("true", "1", "yes", "y", "on"):
        return True
    if lowered in ("false", "0", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"无法解析布尔值 '{text}'（可选 true/false）")
