"""生图标准 MCP 服务 —— 参考实现 / 验收用。

实现了 MamboChat 生图工具标准 v2 的三个固定工具::

    image_generate     prompt / NumxNum / negative_prompt / count / sync / extra
                       -> {task_id, status, count, resolution}
    image_task_status  task_id / wait_timeout
                       -> {task_id, status, progress, count, error}
    image_download     task_id / index -> ImageContent(...)

特点：
- 不依赖任何第三方库（PNG 由标准库 zlib + struct 手工构造），产出纯色占位图。
- 任务状态落在临时目录的 JSON 文件里，因此 **stdio 传输下每次调用重启进程也不会丢状态**
  （标准要求服务自己持久化任务状态，本文件即示范）。
- 支持透传 ``extra``：``width`` / ``height`` / ``color``(r,g,b) / ``fail``。
- 支持 ``NumxNum`` 分辨率，优先级低于显式 ``width`` / ``height``。
- ``image_task_status`` 支持 ``wait_timeout``：阻塞轮询、状态收敛即提前返回。

启动方式（stdio，供 MCP 服务配置使用）::

    command: <python 可执行文件>
    args:    ["<本文件绝对路径>"]
"""

import base64
import json
import os
import re
import struct
import tempfile
import time
import uuid
import zlib
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Image

STATE_DIR = os.path.join(tempfile.gettempdir(), "mambo_image_gen_standard")
TASKS_FILE = os.path.join(STATE_DIR, "tasks.json")
IMAGES_DIR = os.path.join(STATE_DIR, "images")

DEFAULT_SIZE = (512, 512)
DEFAULT_COLOR = (90, 140, 220)
MAX_COUNT = 8
MIN_RESOLUTION = 64
MAX_RESOLUTION = 4096

# 阻塞等待状态的轮询节奏（秒）
POLL_INTERVAL = 0.5
SETTLED_STATUSES = ("completed", "failed", "expired")

_RESOLUTION_RE = re.compile(r"^\s*(\d{1,4})\s*[xX*×:：]\s*(\d{1,4})\s*$")

mcp = FastMCP("image-gen-standard")


def _parse_resolution(value: Any) -> Optional[tuple[int, int]]:
    if value is None:
        return None
    matched = _RESOLUTION_RE.match(str(value))
    if not matched:
        return None
    width, height = int(matched.group(1)), int(matched.group(2))
    if not (MIN_RESOLUTION <= width <= MAX_RESOLUTION):
        return None
    if not (MIN_RESOLUTION <= height <= MAX_RESOLUTION):
        return None
    return width, height


# ---------------------------------------------------------------------------
# 最小 PNG 编码（无第三方依赖）
# ---------------------------------------------------------------------------

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _make_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    row = b"\x00" + bytes(color) * width
    raw = row * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# 任务状态持久化
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    os.makedirs(IMAGES_DIR, exist_ok=True)


def _load_tasks() -> Dict[str, Dict[str, Any]]:
    try:
        with open(TASKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_tasks(tasks: Dict[str, Dict[str, Any]]) -> None:
    _ensure_dirs()
    tmp = f"{TASKS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False)
    os.replace(tmp, TASKS_FILE)


# ---------------------------------------------------------------------------
# 工具：image_generate
# ---------------------------------------------------------------------------

@mcp.tool()
def image_generate(
    prompt: str,
    NumxNum: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    count: int = 1,
    sync: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate placeholder images from a prompt.

    ``NumxNum`` sets the resolution, e.g. "1024x1024" / "768x1344".
    Returns {"task_id": ..., "status": "completed"|"queued", "count": N, "resolution": "WxH"}.
    Extra keys are forwarded verbatim; unknown keys are ignored.
    """
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt 不能为空")

    opts = dict(extra or {})
    size = _parse_resolution(NumxNum) or DEFAULT_SIZE
    width = int(opts.get("width") or size[0])
    height = int(opts.get("height") or size[1])
    color = opts.get("color") or DEFAULT_COLOR
    if not (isinstance(color, (list, tuple)) and len(color) == 3):
        color = DEFAULT_COLOR
    color = tuple(max(0, min(int(c), 255)) for c in color)

    total = max(1, min(int(count or 1), MAX_COUNT))
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    _ensure_dirs()
    files: List[str] = []
    for index in range(total):
        path = os.path.join(IMAGES_DIR, f"{task_id}_{index}.png")
        with open(path, "wb") as f:
            f.write(_make_png(width, height, color))
        files.append(path)

    tasks = _load_tasks()
    failed = bool(opts.get("fail"))
    tasks[task_id] = {
        "task_id": task_id,
        "status": "failed" if failed else "completed",
        "progress": None if failed else 100,
        "count": total,
        "files": files,
        "resolution": f"{width}x{height}",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "error": "extra.fail=true，演示失败返回" if failed else None,
        "created_at": time.time(),
    }
    _save_tasks(tasks)

    return {
        "task_id": task_id,
        "status": tasks[task_id]["status"],
        "count": total,
        "resolution": tasks[task_id]["resolution"],
    }


# ---------------------------------------------------------------------------
# 工具：image_task_status
# ---------------------------------------------------------------------------

def _settled(task: Dict[str, Any]) -> bool:
    if str(task.get("status", "")).lower() in SETTLED_STATUSES:
        return True
    progress = task.get("progress")
    return isinstance(progress, (int, float)) and progress >= 100


@mcp.tool()
def image_task_status(task_id: str, wait_timeout: int = 0) -> Dict[str, Any]:
    """Check task progress.

    ``wait_timeout`` (seconds) blocks up to that long, returning early as soon as
    the task settles (completed / failed / expired / progress 100).
    Returns {"task_id", "status", "progress", "count", "error"}.
    progress may be null when unknown.
    """
    try:
        wait = max(0, int(wait_timeout or 0))
    except (TypeError, ValueError):
        wait = 0

    deadline = time.monotonic() + wait
    while True:
        task = _load_tasks().get(task_id)
        if task is None:
            return {
                "task_id": task_id,
                "status": "expired",
                "progress": None,
                "count": None,
                "error": "任务不存在或已过期",
            }
        if _settled(task) or time.monotonic() >= deadline:
            break
        time.sleep(min(POLL_INTERVAL, max(0.0, deadline - time.monotonic())))

    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "progress": task.get("progress"),
        "count": task.get("count"),
        "error": task.get("error"),
    }


# ---------------------------------------------------------------------------
# 工具：image_download
# ---------------------------------------------------------------------------

@mcp.tool(structured_output=False)
def image_download(task_id: str, index: Optional[int] = None) -> List[Image]:
    """Return the finished images as image content (base64 in-band).

    Returns one ImageContent per image. Never returns a bare URL.
    """
    task = _load_tasks().get(task_id)
    if task is None:
        raise ValueError(f"任务 {task_id} 不存在或已过期")

    paths: List[str] = task.get("files") or []
    if index is not None:
        try:
            paths = [paths[int(index)]]
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"index {index} 超出范围（共 {len(paths)} 张）") from exc

    if not paths:
        raise ValueError(f"任务 {task_id} 没有可下载的图片")

    images: List[Image] = []
    for path in paths:
        with open(path, "rb") as f:
            images.append(Image(data=f.read(), format="png"))
    return images


if __name__ == "__main__":
    mcp.run()
