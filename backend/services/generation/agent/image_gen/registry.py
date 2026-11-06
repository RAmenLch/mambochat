"""生图配置注册表：一个 Agent 可以同时挂多个生图配置。

中间件持有本模块的 :class:`ImageGenEntry` 列表（顺序 = Agent 配置顺序，第一个
即默认），按 LLM 传入的 ``image_generator`` **名称**选择具体实现，并把「名称 +
说明 + 该配置的额外参数」渲染进工具描述，供 LLM 选择。

渲染必须是**确定性**的：同一份配置快照 → 同一段文本（不打散 KV cache），
因此这里不读运行时状态、不发网络请求，顺序也完全由传入列表决定。
"""

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from .standard import (
    GENERATOR_ARG,
    IMAGE_TOOL_GENERATE,
    MAX_GENERATOR_DESC_CHARS,
    MAX_GENERATOR_EXTRA_CHARS,
    ImageGenStandard,
    ImageGenToolError,
)


@dataclass(frozen=True)
class ImageGenEntry:
    """一个生图配置的运行期视图。

    ``name`` 是 ``ImageGenConfig.name``（全局唯一），也就是 LLM 通过
    ``image_generator`` 传入的选择键；``tools`` 是该配置启用的工具名集合。
    """

    name: str
    standard: ImageGenStandard
    description: Optional[str] = None
    tools: Tuple[str, ...] = ()

    def supports(self, tool_name: str) -> bool:
        return tool_name in self.tools


def normalize_generator_name(value: Any) -> str:
    """把名称收敛为可比较形式：压缩空白（含全角空格），仅用于匹配。"""
    return " ".join(str(value or "").replace("\u3000", " ").split())


def entries_for_tool(
    entries: Sequence[ImageGenEntry], tool_name: str
) -> List[ImageGenEntry]:
    """该工具可用的配置（配置级开关决定它是否支持某个工具）。"""
    return [entry for entry in entries if entry.supports(tool_name)]


def pick_generator(
    entries: Sequence[ImageGenEntry], name: Optional[str], tool_name: str
) -> ImageGenEntry:
    """按名称挑配置；名称留空时取该工具候选里的第一个。

    匹配规则（从宽到严依次尝试，避免 LLM 因大小写/空白复制偏差而失败）：
    精确 → 忽略大小写。都不中则报错并列出可选名称，**不做静默回退**，
    以免 LLM 误以为用了自己指定的那个配置。
    """
    candidates = entries_for_tool(entries, tool_name)
    if not candidates:
        raise ImageGenToolError(
            f"没有可用于 {tool_name} 的生图配置，请检查 Agent 的生图设置。"
        )

    wanted = normalize_generator_name(name)
    if not wanted:
        return candidates[0]

    key = wanted.casefold()
    for entry in candidates:
        if normalize_generator_name(entry.name).casefold() == key:
            return entry

    available = " / ".join(f'"{entry.name}"' for entry in candidates)
    raise ImageGenToolError(
        f"未知的生图工具 {wanted!r}。{tool_name} 可用的名称有：{available}；"
        f"不传 {GENERATOR_ARG} 时默认使用 "
        f'"{candidates[0].name}"。'
    )


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def build_generator_catalog(
    entries: Sequence[ImageGenEntry], tool_name: str
) -> str:
    """工具描述末尾的「可用生图工具」清单（含逐配置说明与额外参数）。"""
    candidates = entries_for_tool(entries, tool_name)
    if not candidates:
        return ""

    default_name = candidates[0].name
    lines = [
        f" Image generators available for this tool — pass the exact name as "
        f"'{GENERATOR_ARG}' to choose one; omit it to use \"{default_name}\" "
        f"(the first configured one):"
    ]
    for entry in candidates:
        desc = _truncate(entry.description or "", MAX_GENERATOR_DESC_CHARS) or "no description"
        lines.append(f'  - "{entry.name}": {desc}')
        extra = entry.standard.describe_extra_options()
        if extra:
            lines.append(
                f"    extra: {_truncate(extra, MAX_GENERATOR_EXTRA_CHARS)}"
            )
        if not entry.standard.default_sync:
            lines.append(
                "    behaviour: async — returns status=pending plus the target file "
                "paths immediately; the platform saves and displays the images in the "
                "background (do NOT call show / image_download)."
            )
    return "\n" + "\n".join(lines) + "\n"


def default_entry(
    entries: Sequence[ImageGenEntry], tool_name: str = IMAGE_TOOL_GENERATE
) -> Optional[ImageGenEntry]:
    """该工具的默认配置（第一个候选），没有候选时返回 None。"""
    candidates = entries_for_tool(entries, tool_name)
    return candidates[0] if candidates else None


__all__ = [
    "ImageGenEntry",
    "build_generator_catalog",
    "default_entry",
    "entries_for_tool",
    "normalize_generator_name",
    "pick_generator",
]
