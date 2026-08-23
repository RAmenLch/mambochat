"""路径安全校验工具 — 黑名单策略

只禁止会导致虚拟路径解析失败的字符，放行中文等所有 Unicode 内容。
用于校验 Agent name、Resource name、Skill name、Backend name 等需要
作为虚拟文件系统路径片段使用的字段。
"""

import re
from typing import FrozenSet

# 黑名单：路径分隔符 + 控制字符 + Null
_PATH_UNSAFE_RE = re.compile(r"[/\\\x00-\x1f\x7f]")

# 系统保留字 — 所有 name 类型共享，避免与内部路由/特殊目录碰撞
RESERVED_PATH_NAMES: FrozenSet[str] = frozenset({
    "skills",
    "memories",
    "state",
    "root",
    "tmp",
    "temp",
    "workspace",
    "this_chat_tmp",
    ".mambo",
})


def validate_path_safe_name(v: str, label: str = "名称") -> str:
    """校验 name 是否可作为虚拟路径片段安全使用（黑名单策略）。

    允许中文、日文、Emoji 等所有 Unicode，只禁止：
    - 路径分隔符 `/` `\\`
    - 控制字符 (\\x00-\\x1f, \\x7f)
    - 恰好为 `.` 或 `..`
    - 系统保留字
    - 空字符串或纯空白
    """
    if not v or not v.strip():
        raise ValueError(f"{label} 不能为空")

    if _PATH_UNSAFE_RE.search(v):
        raise ValueError(
            f"{label} 包含非法字符（禁止 / \\ 和控制字符），"
            f"当前值: {v!r}"
        )

    if v in (".", ".."):
        raise ValueError(f'{label} 不能为 "." 或 ".."')

    if v.lower() in RESERVED_PATH_NAMES:
        raise ValueError(
            f"{label} 不能使用系统保留字: "
            f"{', '.join(sorted(RESERVED_PATH_NAMES))}"
        )

    return v
