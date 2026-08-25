"""MamboChat 后端版本号唯一来源。

发版时只需修改 __version__ 一处；其余后端版本标识
（pyproject 动态版本、FastAPI version、CLI __version__、
导出包 mambochatVersion）均从此导入。
"""

__version__ = "1.3.1"
