"""Provider / Model 引用解析（Docker 风格前缀 ID + provider:modelId 命名空间消歧）。

解析优先级（model）:
  1. 完整 UUID（数据库主键）
  2. UUID 前缀（任意长度，唯一即命中，Docker 风格）
  3. provider:modelId 或 provider:name 复合引用
  4. 裸 modelId / name（仅当全局唯一时接受）

所有匹配均以 8 位短 ID 形式展示（与 mambo model list 一致），便于直接引用。
"""
from __future__ import annotations

from typing import Optional


class ResolutionError(Exception):
    """引用无法解析：未找到、前缀过短或存在歧义。"""

    def __init__(self, message: str, candidates: Optional[list[str]] = None):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """带表头的对齐候选表格，供歧义错误消息使用。"""
    import unicodedata

    def width(text) -> int:
        return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))

    widths = [width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], width(cell))

    def render(cells):
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    lines = [render(headers), "  ".join("-" * w for w in widths)] + [render(r) for r in rows]
    return "\n".join("  " + line for line in lines)


def _format_candidates(models: list[dict]) -> str:
    """模型候选表格（列: PROVIDER / MODEL ID / NAME / SHORT ID）。"""
    rows = [
        [
            (m.get("providerId") or "?")[:8],
            m.get("modelId") or "?",
            m.get("name") or "?",
            (m.get("id") or "?")[:8],
        ]
        for m in models
    ]
    return _format_table(["PROVIDER", "MODEL ID", "NAME", "SHORT ID"], rows)


def _format_provider_candidates(providers: list[dict]) -> str:
    """服务商候选表格（列: ID / NAME）。"""
    rows = [
        [(p.get("id") or "?")[:8], p.get("name") or "?"]
        for p in providers
    ]
    return _format_table(["ID", "NAME"], rows)


def _unique_match(matches: list[dict], ref: str, kind: str, hint: str,
                  column_note: str, fmt) -> dict:
    if not matches:
        raise ResolutionError(f"{kind}引用 '{ref}' 未找到。{hint}")
    if len(matches) > 1:
        raise ResolutionError(
            f"{kind}引用 '{ref}' 存在歧义，匹配到 {len(matches)} 项（{column_note}）:\n"
            + fmt(matches)
            + f"\n{hint}"
        )
    return matches[0]


def resolve_provider(providers: list[dict], ref: str) -> dict:
    if not ref:
        raise ResolutionError("服务商引用不能为空。")
    # 1. 精确 ID
    for p in providers:
        if p["id"] == ref:
            return p
    # 2. ID 前缀（唯一即命中；歧义报错）
    matches = [p for p in providers if p["id"].startswith(ref)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResolutionError(
            f"服务商引用 '{ref}' 匹配到多个 ID 前缀（列: ID=服务商短ID / NAME）:\n"
            + _format_provider_candidates(matches)
            + "\n请使用更长的前缀或完整 ID。"
        )
    # 3. 唯一名称
    matches = [p for p in providers if p["name"] == ref]
    return _unique_match(
        matches, ref, "服务商",
        "可用 mambo provider list 查看可用服务商（短ID 见 ID 列）。",
        "列: ID=服务商短ID / NAME",
        _format_provider_candidates,
    )


def _all_models(providers: list[dict]) -> list[dict]:
    return [m for p in providers for m in p.get("models", [])]


def resolve_model(providers: list[dict], ref: str) -> dict:
    if not ref:
        raise ResolutionError("模型引用不能为空。")
    # 1. provider:modelId / provider:name 复合引用
    if ":" in ref:
        provider_ref, _, model_ref = ref.partition(":")
        provider = resolve_provider(providers, provider_ref)
        matches = [
            m for m in provider.get("models", [])
            if m["modelId"] == model_ref or m["name"] == model_ref
        ]
        return _unique_match(
            matches, ref, "模型",
            f"服务商 '{provider['id'][:8]}' 下未找到模型 '{model_ref}'。"
            f"可用 mambo model list --provider {provider['id'][:8]} 查看。",
            "列: PROVIDER=服务商短ID / MODEL ID / NAME / SHORT ID=模型短ID",
            _format_candidates,
        )
    models = _all_models(providers)
    # 2. 完整 UUID
    for m in models:
        if m["id"] == ref:
            return m
    # 3. UUID 前缀（任意长度，唯一即命中）
    matches = [m for m in models if m["id"].startswith(ref)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResolutionError(
            f"模型引用 '{ref}' 匹配到多个 UUID 前缀"
            f"（列: PROVIDER=服务商短ID / MODEL ID / NAME / SHORT ID=模型短ID）:\n"
            + _format_candidates(matches)
            + "\n请使用更长的前缀，或 provider:modelId 形式。"
        )
    # 4. 裸 modelId / name（全局唯一才接受）
    matches = [m for m in models if m["modelId"] == ref or m["name"] == ref]
    return _unique_match(
        matches, ref, "模型",
        "请使用 provider:modelId 形式消歧，如 190c2f0c:deepseek-v4-flash；"
        "或 mambo model list 查看短 ID 与所属服务商。",
        "列: PROVIDER=服务商短ID / MODEL ID / NAME / SHORT ID=模型短ID",
        _format_candidates,
    )


# ---------------------------------------------------------------------------
# Resource 树与路径解析（文件系统式）
# ---------------------------------------------------------------------------

# 目录型: itemType=folder；文件型: itemType=resource
DIRECTORY_TYPES = ("knowledge_base", "skill")  # folder 的 resourceType=None
FILE_TYPES = ("file", "system_prompt", "submessage_template", "kb_file")

TYPE_LABELS = {
    "knowledge_base": "[kb]",
    "skill": "[skill]",
    "file": "[file]",
    "system_prompt": "[prompt]",
    "submessage_template": "[template]",
    "kb_file": "[kb-file]",
}


def is_directory(res: dict) -> bool:
    return res.get("itemType") == "folder"


def resource_type_label(res: dict) -> str:
    if is_directory(res):
        return TYPE_LABELS.get(res.get("resourceType"), "[folder]")
    return TYPE_LABELS.get(res.get("resourceType"), "[file]")


def build_resource_tree(resources: list[dict]):
    """返回 (children_map, roots, by_id)；children 已按 sortOrder/名称排序。"""
    by_id = {r["id"]: r for r in resources}
    children: dict[str | None, list[dict]] = {}
    for r in resources:
        children.setdefault(r.get("parentId"), []).append(r)
    roots = children.pop(None, []) + children.pop("root", [])
    for lst in children.values():
        lst.sort(key=lambda r: (r.get("sortOrder", 0), r.get("name", "")))
    roots.sort(key=lambda r: (r.get("sortOrder", 0), r.get("name", "")))
    return children, roots, by_id


def resource_path_of(resource_id: str, by_id: dict, resources: list[dict]) -> str:
    """从根到该资源的路径字符串，如 /知识库/文档.md。"""
    if resource_id not in by_id:
        return f"/{resource_id[:8]}"
    parts = []
    cur = by_id[resource_id]
    seen = set()
    while cur is not None and cur.get("parentId") and cur["id"] not in seen:
        seen.add(cur["id"])
        parts.append(cur["name"])
        cur = by_id.get(cur.get("parentId"))
    if cur is not None and cur["id"] not in seen:
        parts.append(cur["name"])
    return "/" + "/".join(reversed(parts))


def _candidates_text(resources: list[dict], title: str) -> str:
    """资源候选表格（列: TYPE / NAME / SHORT ID）。"""
    import unicodedata

    def width(text) -> int:
        return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))

    headers = ["TYPE", "NAME", "SHORT ID"]
    rows = [
        [resource_type_label(r), r.get("name") or "?", (r.get("id") or "?")[:8]]
        for r in resources
    ]
    widths = [width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], width(cell))

    def render(cells):
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    lines = [render(headers), "  ".join("-" * w for w in widths)] + [render(r) for r in rows]
    return title + "\n" + "\n".join("  " + line for line in lines)


def resolve_resource(resources: list[dict], ref: str) -> dict:
    """按 短ID / 绝对路径(/a/b) 解析资源。"""
    if not ref:
        raise ResolutionError("资源引用不能为空。")
    # 1. 短 ID 前缀（唯一即命中）
    matches = [r for r in resources if r["id"].startswith(ref)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResolutionError(
            f"资源引用 '{ref}' 匹配到多个 ID 前缀: "
            + ", ".join(m["id"][:8] for m in matches)
            + "。请使用更长的前缀。"
        )
    # 2. 路径
    children, roots, by_id = build_resource_tree(resources)
    nodes = roots
    parts = [p for p in ref.split("/") if p]
    if not parts:
        raise ResolutionError(f"资源引用 '{ref}' 未找到。可用 mambo resource ls 查看。")
    for i, part in enumerate(parts):
        matched = [n for n in nodes if n["name"] == part]
        if not matched:
            raise ResolutionError(
                f"路径 '{ref}' 未找到: 段 '{part}' 不存在。可用 mambo resource ls 查看目录结构。"
            )
        if len(matched) > 1:
            raise ResolutionError(_candidates_text(
                matched, f"路径 '{ref}' 中段 '{part}' 存在同名歧义，匹配到 {len(matched)} 项:",
            ))
        node = matched[0]
        if i == len(parts) - 1:
            return node
        nodes = children.get(node["id"], [])
    raise ResolutionError(f"资源引用 '{ref}' 未找到。")


def resolve_resource_parent(resources: list[dict], ref: str) -> tuple[str | None, str]:
    """解析新建目标的父目录: ref 最后一段为名称，前面为父路径。返回 (parent_id, name)。"""
    parts = [p for p in ref.split("/") if p]
    if not parts:
        raise ResolutionError("路径不能为空。")
    name = parts[-1]
    parent_ref = "/".join(parts[:-1])
    if not parent_ref:
        return None, name
    parent = resolve_resource(resources, parent_ref)
    if not is_directory(parent):
        raise ResolutionError(f"父路径 '{parent_ref}' 不是目录型资源（{resource_type_label(parent)}）。")
    return parent["id"], name
