"""MamboChat 后端版本号。

版本号唯一来源是 backend/_version.txt（发版时只改该文件）：
- pyproject.toml 通过 `[tool.setuptools.dynamic] version = {file = [...]}` 读取，构建时无需 import 本模块
- 本模块运行时读取同一文件，供 FastAPI version / CLI __version__ / 导出包 mambochatVersion 使用
"""

from pathlib import Path

__version__ = Path(__file__).with_name("_version.txt").read_text(encoding="utf-8").strip()
