"""终端输出：人类可读表格 / 键值对，或机器可读 JSON。"""
from __future__ import annotations

import json
import unicodedata
from typing import Callable, Iterable, Optional


def short_id(value) -> str:
    """截取 8 位短 ID，供表格展示与后续引用。"""
    return (value or "")[:8]


def _disp_width(text) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _flatten_cell(text) -> str:
    """表格单元格单行化：折叠换行与连续空白，避免破坏列对齐。"""
    return " ".join(str(text).split())


def print_table(rows: Iterable[dict], columns: list[tuple[str, str, Optional[Callable]]]) -> None:
    """columns: [(key, header, formatter)]，formatter 为 None 时直接 str()。"""
    rows = list(rows)
    headers = [h for _, h, _ in columns]
    cell_rows = []
    for row in rows:
        cells = []
        for key, _h, fmt in columns:
            value = row.get(key)
            cells.append(_flatten_cell(fmt(value) if fmt else ("" if value is None else value)))
        cell_rows.append(cells)

    widths = [_disp_width(h) for h in headers]
    for cells in cell_rows:
        for i, cell in enumerate(cells):
            widths[i] = max(widths[i], _disp_width(cell))

    def render(cells):
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    print(render(headers))
    print("  ".join("-" * w for w in widths))
    if cell_rows:
        for cells in cell_rows:
            print(render(cells))
    else:
        print("(空)")


def print_kv(obj: dict, keys: Optional[Iterable[str]] = None, label: str = "") -> None:
    if label:
        print(label)
    for key in keys or obj.keys():
        value = obj.get(key)
        if value is None:
            print(f"{key}: (null)")
        elif isinstance(value, (dict, list)):
            print(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"{key}: {value}")
