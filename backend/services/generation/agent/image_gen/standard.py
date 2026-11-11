"""生图工具标准框架。

定义三个工具的固定契约（``image_generate`` / ``image_task_status`` /
``image_download``），并实现与协议无关的公共逻辑：参数默认值、输出路径
校验与命名、图片落盘、结果 JSON 组装。

子类只需实现三个原语（``submit`` / ``status`` / ``download``），
协议差异（MCP、内置 HTTP 模型等）全部收敛在子类内部。
"""

import asyncio
import base64
import binascii
import json
import logging
import re
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field, create_model

from mambo_agents.backends.protocol import BackendProtocol
from mambo_agents.backends.schemas import VirtualPath

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具契约
# ---------------------------------------------------------------------------

IMAGE_TOOL_GENERATE = "image_generate"
IMAGE_TOOL_STATUS = "image_task_status"
IMAGE_TOOL_DOWNLOAD = "image_download"

# 契约三件套（MCP 服务必须实现，也是配置检测的唯一依据）
IMAGE_TOOL_NAMES: Tuple[str, ...] = (
    IMAGE_TOOL_GENERATE,
    IMAGE_TOOL_STATUS,
    IMAGE_TOOL_DOWNLOAD,
)

# 平台侧「一条龙」工具：生成 → 落盘 → 入库展示，一步完成。
# 它完全由平台包装上面三个原语实现，MCP 服务无需感知。
IMAGE_TOOL_GENERATE_SHOW = "image_generate_show"

# 产出 FILE 子消息的工具（前端据此把结果渲染成文件/图片）。
# show 是通用展示工具，image_generate_show 是一条龙生图工具。
FILE_OUTPUT_TOOLS: Tuple[str, ...] = ("show", IMAGE_TOOL_GENERATE_SHOW)

# 工作区虚拟根：与 show 工具、agent 默认 workspace_root 保持一致
WORKSPACE_ROOT = "/workspace"

# 默认落地目录（以 “/” 结尾表示目录，见 _normalize_dir）
DEFAULT_OUTPUT_DIR = f"{WORKSPACE_ROOT}/images/"
DEFAULT_PREFIX = "image"
DEFAULT_COUNT = 1
MAX_COUNT = 8
MAX_PREFIX_LEN = 64

# 参考图（契约参数 reference_images）：
#   LLM 侧给 workspace 虚拟路径列表，平台读取后以 MCP ImageContent JSON
#   （{"type": "image", "data": <base64>, "mimeType": ...}）下发给实现类。
REFERENCE_ARG = "reference_images"
MAX_REFERENCE_IMAGES = 8
MAX_REFERENCE_BYTES = 8 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 20 * 1024 * 1024
REFERENCE_MIME_WHITELIST: Tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
)

# 生图工具选择参数名：一个 Agent 可挂多个生图配置，LLM 用它按**配置名称**选择。
# 缺省（None / 空串）时使用该工具候选配置里的第一个。
GENERATOR_ARG = "image_generator"
MAX_GENERATOR_DESC_CHARS = 120
MAX_GENERATOR_EXTRA_CHARS = 200

# 分辨率参数名（契约字段，形如 1024x1024）
RESOLUTION_ARG = "resolution"
EXTRA_ARG = "extra"
DEFAULT_RESOLUTION = "1024x1024"
MIN_RESOLUTION = 64
MAX_RESOLUTION = 4096

# 种子参数名（契约字段）
#   LLM 侧接受 int 或 int[]，`-1` 表示随机；平台归一化为「长度 = count 的数组」再下发，
#   第 i 项对应 index=i 的那张图。数量与 count 不一致时以 count 为准（多则截断、
#   少则补随机），但类型 / 值域错误一律报错。
SEEDS_ARG = "seeds"
SEED_RANDOM = -1
MAX_SEED = 2**31 - 1
_SEEDS_FIELD_DESC = (
    "种子：数字或数字数组，用于复现同一张图。-1 表示随机（平台会解析成具体整数）。"
    "生成张数以 count 为准：seeds 多则忽略多余的、少则补随机。"
    "第 i 个种子对应返回结果里 index=i 的那张图"
)

# 状态工具阻塞等待（秒）
DEFAULT_WAIT_TIMEOUT = 0
MAX_WAIT_TIMEOUT = 300
POLL_INTERVAL = 1.5

# 一条龙工具的默认阻塞上限（秒）：未单独配置且未显式传 timeout 时生效
DEFAULT_ONESHOT_WAIT_TIMEOUT = 60

# 文件名生成模式
#   stamp —— 下载时刻的时间戳命名（三件套沿用，行为不变）
#   task  —— 按 task_id 确定性命名（一条龙使用，下载前即可得知路径）
NAMING_STAMP = "stamp"
NAMING_TASK = "task"

# 确定性命名时用于提前规划路径的兜底扩展名；实际下载后以 blob 上报的 mime 为准
DEFAULT_EXT = ".png"

# 文件名片段（前缀 / 由 path 推断的文件名）的非法字符黑名单：只挡会影响
# 路径解析与跨平台文件名合法性的字符，中文等 Unicode 字符一律放行
_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_RESOLUTION_RE = re.compile(r"^\s*(\d{1,4})\s*[xX*×:：]\s*(\d{1,4})\s*$")

_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
}

# 只有这些后缀会被当成「调用方指定的扩展名」。异步流程要在下载前登记路径，
# 必须让预测与落盘用同一个扩展名，否则会登记 ``x.png`` 却写出 ``x.jpg``，
# 后台轮询器永远等不到文件（详见 TargetPlan 的 ext 说明）。
_IMAGE_EXT_WHITELIST = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
)


class ImageGenerateArgs(BaseModel):
    """``image_generate`` 的参数（锁定，不随 server 上报的 schema 变化）。"""

    prompt: str = Field(description="正向提示词，描述期望生成的画面内容")
    image_generator: Optional[str] = Field(
        default=None,
        description=(
            "要使用的生图工具名称，必须与本工具描述中列出的某个名称完全一致；"
            "不传则使用默认（列表中的第一个）"
        ),
    )
    resolution: str = Field(
        default=DEFAULT_RESOLUTION,
        description=(
            "图片分辨率，格式为 `宽x高`（单位像素），例如 1024x1024、768x1344；"
            f"取值范围 {MIN_RESOLUTION}~{MAX_RESOLUTION}"
        ),
    )
    negative_prompt: Optional[str] = Field(
        default=None, description="反向提示词，描述不希望出现的内容"
    )
    count: int = Field(
        default=DEFAULT_COUNT, description=f"生成数量，1~{MAX_COUNT}"
    )
    seeds: Optional[Union[int, List[int]]] = Field(
        default=None, description=_SEEDS_FIELD_DESC
    )
    sync: Optional[bool] = Field(
        default=None,
        description=(
            "是否同步等待生成完成；false 时立即返回任务 ID，需用状态工具查询。"
            "不传则使用配置的默认值"
        ),
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "透传给生图后端的额外参数（如 width/height/steps/seed/model 等）。"
            "平台会原样透传给生图后端，与标准参数同名的键会被忽略"
        ),
    )


class ImageStatusArgs(BaseModel):
    """``image_task_status`` 的参数。"""

    task_id: str = Field(description="``image_generate`` 返回的任务 ID")
    wait_timeout: int = Field(
        default=DEFAULT_WAIT_TIMEOUT,
        description=(
            "阻塞等待秒数，0 表示立即返回当前状态；大于 0 时最多阻塞这么多秒，"
            "任务提前完成（成功/失败/进度 100%）则立即返回"
        ),
    )


class ImageDownloadArgs(BaseModel):
    """``image_download`` 的参数。"""

    task_id: str = Field(description="``image_generate`` 返回的任务 ID")
    index: Optional[int] = Field(
        default=None, description="仅下载指定下标（从 0 开始）的图片；不传则下载全部"
    )
    wait_timeout: int = Field(
        default=DEFAULT_WAIT_TIMEOUT,
        description=(
            "下载前阻塞等待秒数，0 表示不等待；大于 0 时先等任务完成再取图"
        ),
    )
    path: str = Field(
        description=(
            f"目标目录虚拟路径，必填且必须位于 {WORKSPACE_ROOT} 之下，"
            f"**目录必须以 / 结尾**（例如 {DEFAULT_OUTPUT_DIR}）；"
            "缺省、不以 / 结尾或越界都会直接报错"
        )
    )
    prefix: Optional[str] = Field(
        default=None,
        description=(
            f"文件名前缀，缺省为 {DEFAULT_PREFIX}。支持中文等 Unicode 字符，"
            '仅禁止 \\ / : * ? " < > | 等路径/文件系统非法字符'
        ),
    )


class ImageGenerateShowArgs(BaseModel):
    """``image_generate_show`` 的参数（一条龙：生成 + 落盘 + 展示）。"""

    prompt: str = Field(description="正向提示词，描述期望生成的画面内容")
    image_generator: Optional[str] = Field(
        default=None,
        description=(
            "要使用的生图工具名称，必须与本工具描述中列出的某个名称完全一致；"
            "不传则使用默认（列表中的第一个）"
        ),
    )
    resolution: str = Field(
        default=DEFAULT_RESOLUTION,
        description=(
            "图片分辨率，格式为 `宽x高`（单位像素），例如 1024x1024、768x1344；"
            f"取值范围 {MIN_RESOLUTION}~{MAX_RESOLUTION}"
        ),
    )
    negative_prompt: Optional[str] = Field(
        default=None, description="反向提示词，描述不希望出现的内容"
    )
    count: int = Field(
        default=DEFAULT_COUNT, description=f"生成数量，1~{MAX_COUNT}"
    )
    seeds: Optional[Union[int, List[int]]] = Field(
        default=None, description=_SEEDS_FIELD_DESC
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "透传给生图后端的额外参数（如 width/height/steps/seed/model 等）。"
            "平台会原样透传给生图后端，与标准参数同名的键会被忽略"
        ),
    )
    mode: Literal["Normal", "Mini_Avatar", "Gal_Avatar", "Group", "Spark"] = Field(
        default="Normal",
        description=(
            "Display mode for the generated image:\n"
            "- Normal: default inline file display\n"
            "- Mini_Avatar: use image as conversation AI avatar\n"
            "- Gal_Avatar: pin image to left side above toolbar, push AI messages right\n"
            "- Group: group consecutive File images, allow user to pin one to top\n"
            "- Spark: hide all other content (text/reasoning/tools), only show Spark + Group files"
        ),
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            f"图片落地路径的虚拟路径，缺省为 {DEFAULT_OUTPUT_DIR}；"
            f"必须位于 {WORKSPACE_ROOT} 之下。**以 / 结尾表示目录**（如 "
            f"{DEFAULT_OUTPUT_DIR}）；不以 / 结尾则末段视为文件名（如 "
            f"{DEFAULT_OUTPUT_DIR}fox.png 或 {DEFAULT_OUTPUT_DIR}fox），"
            "目录取父级、末段（去扩展名）作文件名前缀"
        ),
    )
    timeout: Optional[int] = Field(
        default=None,
        description=(
            "本次等待生成完成的最长秒数；不传则使用配置的等待时长"
            f"（{MAX_WAIT_TIMEOUT} 秒封顶）"
        ),
    )


# ---------------------------------------------------------------------------
# 参考图参数（按后端能力动态挂在 args schema 上）
# ---------------------------------------------------------------------------

_REFERENCE_FIELD = (
    Optional[List[str]],
    Field(
        default=None,
        description=(
            "参考图列表：工作区（/workspace 之下）虚拟路径数组，例如 "
            "[\"/.mambo/chat_user_file/xxx.png\"]。用于图生图 / 风格或人物参考。"
            f"最多 {MAX_REFERENCE_IMAGES} 张，单张 ≤ "
            f"{MAX_REFERENCE_BYTES // (1024 * 1024)}MB、合计 ≤ "
            f"{MAX_REFERENCE_TOTAL_BYTES // (1024 * 1024)}MB，仅支持 "
            "png / jpeg / webp / gif / bmp。超出限制或文件不存在会直接报错。"
        ),
    ),
)

_REF_ARGS_CACHE: Dict[str, Any] = {}


def _args_model_with_refs(base: type, name: str) -> type:
    """在锁定的 args 模型上追加 ``reference_images``，并按名字缓存。"""
    cached = _REF_ARGS_CACHE.get(name)
    if cached is None:
        cached = create_model(name, __base__=base, reference_images=_REFERENCE_FIELD)
        _REF_ARGS_CACHE[name] = cached
    return cached


def generate_args_model(with_reference: bool) -> type:
    """``image_generate`` 的参数模型：后端不支持参考图时该参数完全不出现。"""
    if not with_reference:
        return ImageGenerateArgs
    return _args_model_with_refs(ImageGenerateArgs, "ImageGenerateArgsRef")


def generate_show_args_model(with_reference: bool) -> type:
    """``image_generate_show`` 的参数模型（同上）。"""
    if not with_reference:
        return ImageGenerateShowArgs
    return _args_model_with_refs(ImageGenerateShowArgs, "ImageGenerateShowArgsRef")


# ---------------------------------------------------------------------------
# 分辨率解析
# ---------------------------------------------------------------------------


def parse_resolution(value: Any) -> Optional[Tuple[int, int]]:
    """把 ``"1024x1024"`` 之类的分辨率字符串解析为 ``(width, height)``。

    无法识别或越界时返回 ``None``（调用方自行决定降级策略）。
    """
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


def format_resolution(width: int, height: int) -> str:
    return f"{width}x{height}"


# ---------------------------------------------------------------------------
# 种子解析与归一化
# ---------------------------------------------------------------------------


def random_seed() -> int:
    """生成一个跨后端通用的随机种子（0 ~ MAX_SEED）。"""
    return secrets.randbelow(MAX_SEED + 1)


def parse_seed(value: Any) -> int:
    """把单个种子收敛为整数；类型 / 值域不合法直接报错。

    ``-1`` 表示随机，交给 :func:`normalize_seeds` 解析成具体整数。
    """
    if isinstance(value, bool):
        raise ImageGenToolError(f"种子必须是整数，收到布尔值: {value!r}")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ImageGenToolError("种子不能是空字符串")
        try:
            value = int(text)
        except ValueError as exc:
            raise ImageGenToolError(f"种子必须是整数，收到: {value!r}") from exc
    if isinstance(value, float):
        if not value.is_integer():
            raise ImageGenToolError(f"种子必须是整数，收到: {value!r}")
        value = int(value)
    if not isinstance(value, int):
        raise ImageGenToolError(f"种子必须是整数，收到: {type(value).__name__}")
    if value == SEED_RANDOM:
        return SEED_RANDOM
    if not (0 <= value <= MAX_SEED):
        raise ImageGenToolError(
            f"种子取值必须是 -1（随机）或 0~{MAX_SEED}，收到: {value}"
        )
    return value


def normalize_seeds(value: Any, count: int) -> Optional[List[int]]:
    """把 LLM 传入的 ``seeds`` 归一化为「长度 = count」的整数数组。

    返回 ``None`` 表示调用方没传种子（此时不下发、也不在结果里回填）。
    数量与 ``count`` 不一致时**以 count 为准**：多则截断，少则补随机；
    但类型 / 值域错误一律报错（不静默纠正）。
    """
    if value is None:
        return None

    raw_items = list(value) if isinstance(value, (list, tuple)) else [value]
    parsed = [parse_seed(item) for item in raw_items if item is not None]
    if not parsed:
        return None

    total = max(1, int(count))
    resolved = [
        random_seed() if seed == SEED_RANDOM else seed for seed in parsed[:total]
    ]
    while len(resolved) < total:
        resolved.append(random_seed())
    return resolved


def seeds_payload(seeds: Optional[List[int]]) -> Optional[List[Dict[str, int]]]:
    """把种子数组转成「图片 ↔ 种子」显式关联的返回结构。"""
    if not seeds:
        return None
    return [{"index": index, "seed": int(seed)} for index, seed in enumerate(seeds)]


def parse_seeds(payload: Any, count: Optional[int] = None) -> Optional[List[Dict[str, int]]]:
    """从后端 payload 里读出种子，并统一成 ``[{index, seed}]``。

    兼容两种形状：``[{"index": 0, "seed": 1}]`` 与裸数组 ``[1, 2]``（按下标隐式对应）。
    无法识别时返回 ``None``（后端不支持种子）。
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get(SEEDS_ARG)
    if raw is None:
        return None
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return None

    items: List[Dict[str, int]] = []
    for position, item in enumerate(raw):
        if isinstance(item, dict):
            index = item.get("index", position)
            seed = item.get("seed")
        else:
            index, seed = position, item
        if isinstance(seed, bool) or seed is None:
            continue
        try:
            seed_value = int(seed)
            index_value = int(index)
        except (TypeError, ValueError):
            continue
        items.append({"index": index_value, "seed": seed_value})

    if not items:
        return None
    if count is not None:
        items = [item for item in items if 0 <= item["index"] < int(count)]
    return items or None


def seeds_by_index(seeds: Optional[List[Dict[str, int]]]) -> Dict[int, int]:
    """把 ``[{index, seed}]`` 转成 ``index → seed`` 映射，便于按图取种子。"""
    return {int(item["index"]): int(item["seed"]) for item in seeds or []}


def attach_file_seeds(
    files: List[Dict[str, Any]],
    seed_map: Optional[Dict[int, int]],
) -> List[Dict[str, Any]]:
    """给 ``files`` 的每一条按 ``index`` 回填 ``seed``（未知时为 ``None``）。

    关联靠 ``index`` 而不是列表顺序：即使部分图片落盘失败、顺序被打乱，
    「这张图用的是哪颗种子」也不会错位。
    """
    seeds = dict(seed_map or {})
    enriched: List[Dict[str, Any]] = []
    for item in files:
        entry = dict(item)
        try:
            index: Optional[int] = int(entry.get("index"))
        except (TypeError, ValueError):
            index = None
        entry["seed"] = seeds.get(index) if index is not None else None
        enriched.append(entry)
    return enriched


def pending_file_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从一条龙的 ``pending`` 结果里取出待生成文件清单。

    每项形如 ``{"index": 0, "path": "/workspace/images/a_0.png", "seed": 123}``：
    平台据此为每张图登记一条待生成文件子消息，并把随机种子一并存档。
    兼容只有 ``paths`` 的旧结果（此时 ``index`` 即 ``paths`` 的下标）。
    """
    files = payload.get("files")
    if isinstance(files, list) and files:
        entries: List[Dict[str, Any]] = []
        for position, item in enumerate(files):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            try:
                index = int(item.get("index", position))
            except (TypeError, ValueError):
                index = position
            entries.append(
                {"index": index, "path": str(item["path"]), "seed": item.get("seed")}
            )
        if entries:
            return entries

    seeds = seeds_by_index(parse_seeds(payload))
    raw_paths = payload.get("paths") or (
        [payload["path"]] if payload.get("path") else []
    )
    return [
        {"index": position, "path": str(path), "seed": seeds.get(position)}
        for position, path in enumerate(raw_paths)
        if path
    ]


def file_seeds(payload: Dict[str, Any]) -> Dict[str, int]:
    """从一条龙 ``completed`` 结果的 ``files`` 里取 ``file_id → seed``。

    同步模式下图片已经落盘入库，前端要显示「这张图用的哪颗种子」，
    关联同样按 ``file_id`` 显式给出，不依赖列表顺序。
    """
    mapping: Dict[str, int] = {}
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        file_id = item.get("file_id")
        seed = item.get("seed")
        if not isinstance(file_id, str) or not file_id or seed is None:
            continue
        try:
            mapping[file_id] = int(seed)
        except (TypeError, ValueError):
            continue
    return mapping



# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ImageBlob:
    """一张待落盘的图片数据。

    ``seed`` 为该图实际使用的种子（后端回报或平台下发值），未知时为 ``None``；
    它随 ``files`` 一起返回，用于把「图 ↔ 种子」的关联直接带出去。
    """

    index: int
    mime_type: str
    base64_data: str
    seed: Optional[int] = None

    @property
    def extension(self) -> str:
        mime = (self.mime_type or "").split(";")[0].strip().lower()
        return _MIME_EXT.get(mime, ".png")


class ImageGenToolError(Exception):
    """生图后端返回的业务错误（可直接展示给 LLM）。"""


@dataclass
class RefImage:
    """一张参考图（已读取并 base64 编码，协议无关）。

    下发实现类时统一转成 MCP ``ImageContent`` 的 JSON 形状
    （``{"type": "image", "data": ..., "mimeType": ...}``），
    这样服务端可直接用 ``list[mcp.types.ImageContent]`` 声明参数并被校验。
    """

    index: int
    mime_type: str
    base64_data: str

    def to_content(self) -> Dict[str, Any]:
        return {
            "type": "image",
            "data": self.base64_data,
            "mimeType": self.mime_type,
        }


def _sanitize_token(value: Any, fallback: str = "task") -> str:
    """把任意 task_id 收敛为可安全用于文件名的片段。"""
    text = str(value or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", text).strip("_")
    return cleaned[:64] or fallback


@dataclass
class ImageTarget:
    """一张图片的确定落盘位置（下载前即可算出）。"""

    path: VirtualPath
    index: int
    mime_type: str
    extension: str


@dataclass
class TargetPlan:
    """落盘路径规划器。

    既可以「下载前预测路径」（``predict``，供“先登记、后落盘”的异步流程使用），
    也可以「拿到真实 blob 后物化路径」（``resolve``，扩展名以 blob 上报的 mime 为准）。

    ``multi`` 显式锁定「是否带多图下标后缀」：异步流程在下载前就已登记路径，
    必须保证之后落盘用的判断一致（否则服务少返回几张图时文件名会对不上）。

    ``ext`` 同理锁定「扩展名」：非空时 ``predict`` 与 ``resolve`` 都用它，
    保证「下载前登记的路径」与「下载后真正写出的路径」逐字节一致。它来自
    调用方在 ``path`` 里显式写的图片后缀（如 ``.../凛.jpg``）；未指定时
    ``predict`` 兜底 ``DEFAULT_EXT``、``resolve`` 以 blob 上报的 mime 为准。
    """

    task_id: str
    output_dir: str
    prefix: str
    naming: str
    stamp: str
    ext: Optional[str] = None
    multi: Optional[bool] = None

    def _filename(self, index: int, multi: bool, extension: str) -> str:
        suffix = f"_{index}" if multi else ""
        if self.naming == NAMING_TASK:
            token = _sanitize_token(self.task_id)
        else:
            token = self.stamp
        return f"{self.prefix}_{token}{suffix}{extension}"

    def _is_multi(self, blob_count: int) -> bool:
        return self.multi if self.multi is not None else blob_count > 1

    def resolve(self, blobs: List[ImageBlob]) -> List[Tuple[ImageTarget, ImageBlob]]:
        """按真实 blob 列表物化路径（扩展名优先取显式 ``ext``，否则取 blob 的 mime）。

        显式 ``ext`` 优先是有意为之：异步流程已经按它在下载前登记了路径，
        这里若改用 blob 的扩展名就会写出另一个文件名，轮询器再也等不到文件。
        内容与后缀不符无妨——入库时 ``resolve_mime`` 会按文件头校正 mime。

        服务实际产出的张数可能超出预期（例如请求 1 张却返回 2 张）：此时若
        仍不带下标后缀，多张图会撞成同一个文件名互相覆盖，因此统一降级为
        带下标的形式。
        """
        multi = self._is_multi(len(blobs))
        filenames = [self._filename(blob.index, multi, self._blob_ext(blob)) for blob in blobs]
        if len(set(filenames)) != len(filenames):
            multi = True
            filenames = [
                self._filename(blob.index, multi, self._blob_ext(blob)) for blob in blobs
            ]

        resolved: List[Tuple[ImageTarget, ImageBlob]] = []
        for blob, filename in zip(blobs, filenames):
            target = ImageTarget(
                path=VirtualPath(f"{self.output_dir}/{filename}"),
                index=blob.index,
                mime_type=blob.mime_type,
                extension=self._blob_ext(blob),
            )
            resolved.append((target, blob))
        return resolved

    def _blob_ext(self, blob: ImageBlob) -> str:
        """单张图的实际扩展名：显式 ``ext`` 优先，否则用 blob 的 mime 推断。"""
        return self.ext or blob.extension

    def predict(self, count: int) -> List[ImageTarget]:
        """不联网地预测 ``count`` 张图片的落盘路径（扩展名取兜底值）。"""
        multi = self._is_multi(count)
        extension = self.ext or DEFAULT_EXT
        return [
            ImageTarget(
                path=VirtualPath(
                    f"{self.output_dir}/{self._filename(index, multi, extension)}"
                ),
                index=index,
                mime_type="",
                extension=extension,
            )
            for index in range(max(1, count))
        ]


@dataclass
class DownloadOutcome:
    """一次下载的结果。"""

    files: List[Dict[str, Any]]
    errors: List[str]
    items: List[Tuple[ImageTarget, bytes]]


def is_settled(payload: Dict[str, Any]) -> bool:
    """任务是否已收敛（完成 / 失败 / 过期 / 进度 100）。

    平台侧后台轮询器驱动「先登记、后落盘」的异步下载时需要这个判断，
    因此在这里提供一个与实现无关的公开入口。
    """
    return ImageGenStandard._is_settled(payload)


def ext_from_path(path: str) -> Optional[str]:
    """取路径里的显式图片扩展名（``.../凛.jpg`` → ``.jpg``）。

    平台侧轮询器重建落盘计划时必须用**登记时的同一个扩展名**，
    否则会写到另一个文件名上，登记路径永远等不到文件。
    """
    name = str(path or "").rsplit("/", 1)[-1]
    if "." not in name:
        return None
    ext = f".{name.rsplit('.', 1)[-1]}".lower()
    return ext if ext in _IMAGE_EXT_WHITELIST else None


# ---------------------------------------------------------------------------
# 标准框架
# ---------------------------------------------------------------------------


class ImageGenStandard(ABC):
    """生图工具标准框架（协议无关）。

    Parameters
    ----------
    default_count:
        未指定 ``count`` 时的默认生成数量。
    default_sync:
        未指定 ``sync`` 时的默认值。
    default_resolution:
        未指定 ``resolution`` 时的默认分辨率，形如 ``1024x1024``。
    default_wait_timeout:
        未指定 ``wait_timeout`` 时的默认阻塞秒数。
    supports_reference_images:
        该实现是否支持参考图（``reference_images``）。为 False 时该参数不会
        出现在工具 schema 里，LLM 无从传入。
    generator_name:
        该实现对应的生图配置名称（即 LLM 通过 ``image_generator`` 传入的选择键）。
        异步流程把它写进 pending 结果，后台轮询器据此还原同一份配置。

    注：图片落地目录完全由 LLM 通过 ``image_download.path`` 指定，
    缺失或越界一律报错，框架不做任何回退。
    """

    def __init__(
        self,
        *,
        default_count: int = DEFAULT_COUNT,
        default_sync: bool = True,
        default_resolution: str = DEFAULT_RESOLUTION,
        default_wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
        supports_reference_images: bool = False,
        generator_name: Optional[str] = None,
    ) -> None:
        self._default_count = max(1, min(int(default_count or DEFAULT_COUNT), MAX_COUNT))
        self._default_sync = bool(default_sync)
        self._default_resolution = self._normalize_resolution(default_resolution)
        self._default_wait_timeout = self._clamp_wait_timeout(default_wait_timeout)
        self._supports_reference_images = bool(supports_reference_images)
        self._generator_name = (generator_name or "").strip() or None

    # ------------------------------------------------------------------
    # 子类原语
    # ------------------------------------------------------------------

    @property
    def generator_name(self) -> Optional[str]:
        """该实现对应的生图配置名称（LLM 的 ``image_generator`` 选择键）。"""
        return self._generator_name

    @property
    def default_sync(self) -> bool:
        """是否为同步模式（False 时一条龙走「登记 pending + 后台下载」）。"""
        return self._default_sync

    @property
    def supports_reference_images(self) -> bool:
        """是否支持参考图；不支持时工具 schema 里不会出现该参数。"""
        return self._supports_reference_images

    @property
    def reference_required(self) -> bool:
        """该后端是否**必须**带参考图（如某些编辑类模型 ``input_references.min >= 1``）。"""
        return False

    def describe_extra_options(self) -> str:
        """拼进工具描述末尾的「额外参数」提示；默认空串（保持既有描述逐字节不变）。

        实现方必须保证**确定性**：同一份配置快照渲染出同一段文本，且渲染时不得发起
        网络请求或读取运行时状态 —— 否则会打散会话的 KV cache。
        """
        return ""

    @abstractmethod
    async def submit(
        self,
        prompt: str,
        negative_prompt: Optional[str],
        count: int,
        sync: bool,
        extra: Dict[str, Any],
        resolution: Optional[str] = None,
        reference_images: Optional[List[RefImage]] = None,
        seeds: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """提交生成任务，返回至少包含 ``task_id`` 的字典。

        ``resolution`` 已归一化为 ``宽x高`` 形式（缺省时由框架填入默认值）；
        ``reference_images`` 已由框架读取为 base64，实现类只需按协议下发。

        ``seeds`` 已归一化为「长度 = count」的整数数组（`-1` 已解析成具体值），
        第 i 项对应 index=i 的那张图。实现类若真正下发了种子，**必须在返回
        字典里带回 ``seeds``**（``[{index, seed}]`` 或裸数组均可），否则平台会认为
        该后端不支持种子并返回 ``seeds: null``；状态接口同理。
        """

    @abstractmethod
    async def status(
        self, task_id: str, wait_timeout: int = DEFAULT_WAIT_TIMEOUT
    ) -> Dict[str, Any]:
        """查询任务状态，返回至少包含 ``task_id`` / ``status`` 的字典。"""

    @abstractmethod
    async def download(
        self, task_id: str, index: Optional[int] = None
    ) -> List[ImageBlob]:
        """取回任务产出的图片数据。"""

    # ------------------------------------------------------------------
    # 工具入口（中间件直接调用）
    # ------------------------------------------------------------------

    async def run_generate(
        self,
        backend: Optional[BackendProtocol],
        args: ImageGenerateArgs,
    ) -> str:
        count = self._clamp_count(args.count)
        resolution = self._normalize_resolution(args.resolution)
        seeds = normalize_seeds(getattr(args, SEEDS_ARG, None), count)
        extra = self._merge_extra(args.extra, resolution, has_seeds=seeds is not None)
        sync = self._default_sync if args.sync is None else bool(args.sync)
        reference_images = await self._load_reference_images(
            backend, getattr(args, REFERENCE_ARG, None)
        )
        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=sync,
            extra=extra,
            resolution=resolution,
            reference_images=reference_images,
            seeds=seeds,
        )
        task_id = self._require_task_id(payload)
        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": payload.get("status") or ("queued" if not sync else "completed"),
            "count": count,
            "resolution": resolution,
        }
        # 后端回报的种子优先；未回报说明该后端没有真正使用种子（不支持则忽略）
        result[SEEDS_ARG] = parse_seeds(payload, count)
        if reference_images:
            result["reference_count"] = len(reference_images)
        if payload.get("error"):
            result["error"] = payload["error"]
        return self._dumps(result)

    async def run_status(self, args: ImageStatusArgs) -> str:
        wait_timeout = self._clamp_wait_timeout(args.wait_timeout)
        payload = await self._status_until_settled(args.task_id, wait_timeout)
        result: Dict[str, Any] = {
            "task_id": payload.get("task_id") or args.task_id,
            "status": self._normalize_status(payload.get("status")),
            "progress": self._normalize_progress(payload.get("progress")),
            "count": payload.get("count"),
            "error": payload.get("error"),
            "seeds": parse_seeds(payload),
        }
        return self._dumps(result)

    async def run_download(
        self, backend: Optional[BackendProtocol], args: ImageDownloadArgs
    ) -> str:
        backend = self._require_backend(backend)

        if not (args.path or "").strip().endswith("/"):
            raise ImageGenToolError(
                f"image_download 的 path 是目标目录，必须以 / 结尾"
                f"（例如 {DEFAULT_OUTPUT_DIR}），收到: {args.path!r}"
            )

        settled = await self._status_until_settled(
            args.task_id, self._clamp_wait_timeout(args.wait_timeout)
        )

        plan = self.plan_targets(
            task_id=args.task_id,
            path=args.path,
            prefix=args.prefix,
            naming=NAMING_STAMP,
        )
        outcome = await self.download_to(
            backend,
            args.task_id,
            plan,
            index=args.index,
            seeds=seeds_by_index(parse_seeds(settled)),
        )
        if not outcome.files:
            raise ImageGenToolError(
                "图片保存失败: "
                + ("; ".join(outcome.errors) if outcome.errors else "未知原因")
            )

        result: Dict[str, Any] = {"task_id": args.task_id, "files": outcome.files}
        if outcome.errors:
            result["errors"] = outcome.errors
        return self._dumps(result)

    async def run_generate_show(
        self,
        backend: Optional[BackendProtocol],
        session_factory: Optional[Callable[[], Any]],
        args: ImageGenerateShowArgs,
    ) -> str:
        """一条龙：生成 → 等待 → 确定性命名落盘 → 入库 → 返回 file_id。

        异步模式（配置 ``defaultSync=false``）下只提交任务并返回全部确定路径，
        落盘与展示交给平台后台轮询器，LLM 无需再调用其它工具；同步模式下
        超时仍未收敛时不落盘，返回 ``task_id`` 让 LLM 退回三件套继续。
        """
        backend = self._require_backend(backend)
        if session_factory is None:
            raise ImageGenToolError(
                "当前会话无法访问文件库，无法展示生成的图片。请检查服务端配置。"
            )

        count = self._clamp_count(args.count)
        resolution = self._normalize_resolution(args.resolution)
        seeds = normalize_seeds(getattr(args, SEEDS_ARG, None), count)
        extra = self._merge_extra(args.extra, resolution, has_seeds=seeds is not None)
        reference_images = await self._load_reference_images(
            backend, getattr(args, REFERENCE_ARG, None)
        )

        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=self._default_sync,
            extra=extra,
            resolution=resolution,
            reference_images=reference_images,
            seeds=seeds,
        )
        task_id = self._require_task_id(payload)
        timeout = self._resolve_oneshot_timeout(args.timeout)
        plan = self.plan_targets(
            task_id=task_id,
            path=args.path or DEFAULT_OUTPUT_DIR,
            naming=NAMING_TASK,
            multi=count > 1,
        )

        if not self._default_sync:
            return self._dumps(
                self._pending_result(
                    task_id,
                    plan,
                    count,
                    resolution,
                    timeout,
                    args,
                    parse_seeds(payload, count),
                )
            )

        settled = await self._status_until_settled(task_id, timeout)
        status = self._normalize_status(settled.get("status"))
        if status in ("failed", "expired"):
            raise ImageGenToolError(
                f"生成任务 {task_id} {status}: "
                + str(settled.get("error") or "后端未提供失败原因")
            )
        if not self._is_settled(settled):
            return self._dumps(
                {
                    "task_id": task_id,
                    "status": status,
                    "progress": self._normalize_progress(settled.get("progress")),
                    "count": count,
                    "resolution": resolution,
                    "files": [],
                    "mode": args.mode,
                    "seeds": parse_seeds(settled, count),
                    "note": (
                        f"生成未在 {timeout} 秒内完成，图片尚未就绪。"
                        "请稍后用 image_task_status(wait_timeout=30) 查询进度，"
                        "完成后再用 image_download 取图并调用 show 展示。"
                    ),
                }
            )

        seed_map = seeds_by_index(parse_seeds(settled, count))
        outcome = await self.download_to(
            backend, task_id, plan, seeds=seed_map or None
        )
        if not outcome.items:
            raise ImageGenToolError(
                "图片保存失败: "
                + ("; ".join(outcome.errors) if outcome.errors else "未知原因")
            )

        from .sink import persist_uploaded

        files, persist_errors = await persist_uploaded(session_factory, outcome.items)
        if not files:
            reason = "; ".join(persist_errors or outcome.errors) or "未知原因"
            raise ImageGenToolError(f"图片入库失败: {reason}")

        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": "completed",
            "count": count,
            "resolution": resolution,
            "mode": args.mode,
            "files": attach_file_seeds(
                files, seeds_by_index(parse_seeds(settled, count))
            ),
        }
        errors = outcome.errors + persist_errors
        if errors:
            result["errors"] = errors
        return self._dumps(result)

    async def run_pending(
        self,
        backend: Optional[BackendProtocol],
        args: ImageGenerateShowArgs,
    ) -> str:
        """只提交任务并返回「待生成」结果，**不做任何等待与下载**。

        与 agent 异步模式下的 ``image_generate_show`` 结果完全同形：给出
        ``task_id`` 与全部确定路径，落盘 / 入库交给平台后台轮询器。平台重跑
        走这条入口，保证「请求线程只提交、轮询器只下载」，不会重复取图。
        """
        count = self._clamp_count(args.count)
        resolution = self._normalize_resolution(args.resolution)
        seeds = normalize_seeds(getattr(args, SEEDS_ARG, None), count)
        extra = self._merge_extra(args.extra, resolution, has_seeds=seeds is not None)
        timeout = self._resolve_oneshot_timeout(args.timeout)
        reference_images = await self._load_reference_images(
            backend, getattr(args, REFERENCE_ARG, None)
        )

        payload = await self.submit(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            count=count,
            sync=False,
            extra=extra,
            resolution=resolution,
            reference_images=reference_images,
            seeds=seeds,
        )
        task_id = self._require_task_id(payload)
        plan = self.plan_targets(
            task_id=task_id,
            path=args.path or DEFAULT_OUTPUT_DIR,
            naming=NAMING_TASK,
            multi=count > 1,
        )
        return self._dumps(
            self._pending_result(
                task_id,
                plan,
                count,
                resolution,
                timeout,
                args,
                parse_seeds(payload, count),
            )
        )

    # ------------------------------------------------------------------
    # 公共工具方法
    # ------------------------------------------------------------------

    def _clamp_count(self, count: Optional[int]) -> int:
        if count is None:
            return self._default_count
        try:
            value = int(count)
        except (TypeError, ValueError):
            return self._default_count
        return max(1, min(value, MAX_COUNT))

    def _merge_extra(
        self,
        extra: Optional[Dict[str, Any]],
        resolution: Optional[str] = None,
        *,
        has_seeds: bool = False,
    ) -> Dict[str, Any]:
        """过滤掉与标准参数同名的键，并把分辨率解析为 width/height 合并进去。

        ``extra`` 中显式给出的 ``width`` / ``height`` 优先级高于 ``resolution``。
        调用方已用 ``seeds`` 指定种子时，``extra.seed`` 被丢弃，避免同一颗种子
        从两条通道下发（契约字段优先）。
        """
        reserved = {
            "prompt",
            "negative_prompt",
            "count",
            "sync",
            "task_id",
            EXTRA_ARG,
            "wait_timeout",
            RESOLUTION_ARG,
            REFERENCE_ARG,
            SEEDS_ARG,
            # 平台侧参数：仅用于落盘与展示，不该下发给服务
            GENERATOR_ARG,
            "mode",
            "path",
            "prefix",
        }
        merged = {k: v for k, v in (extra or {}).items() if k not in reserved}
        if has_seeds:
            merged.pop("seed", None)

        size = parse_resolution(resolution)
        if size is not None:
            width, height = size
            merged.setdefault("width", width)
            merged.setdefault("height", height)
        return merged

    async def _load_reference_images(
        self,
        backend: Optional[BackendProtocol],
        paths: Optional[List[str]],
    ) -> Optional[List[RefImage]]:
        """把 LLM 给的 workspace 路径读成 base64 参考图，任何问题都直接报错。"""
        raw_paths = [str(p).strip() for p in (paths or []) if str(p or "").strip()]
        if not raw_paths:
            return None

        if not self.supports_reference_images:
            raise ImageGenToolError(
                "当前生图后端不支持参考图（reference_images），请移除该参数后重试。"
            )

        if len(raw_paths) > MAX_REFERENCE_IMAGES:
            raise ImageGenToolError(
                f"参考图最多 {MAX_REFERENCE_IMAGES} 张，收到 {len(raw_paths)} 张。"
            )

        # 先校验路径形态，再要求 backend（路径错误与后端缺失是两类问题）
        validated = [self._validate_reference_path(raw) for raw in raw_paths]
        backend = self._require_backend(backend)

        from .sink import read_workspace_file, resolve_mime

        images: List[RefImage] = []
        total_bytes = 0
        for index, path in enumerate(validated):
            data, error = await read_workspace_file(backend, path)
            if error:
                raise ImageGenToolError(f"读取参考图 {path} 失败: {error}")
            if not data:
                raise ImageGenToolError(f"参考图 {path} 内容为空")

            size = len(data)
            if size > MAX_REFERENCE_BYTES:
                raise ImageGenToolError(
                    f"参考图 {path} 体积 {size / 1024 / 1024:.1f}MB 超过单张上限 "
                    f"{MAX_REFERENCE_BYTES // (1024 * 1024)}MB"
                )
            total_bytes += size
            if total_bytes > MAX_REFERENCE_TOTAL_BYTES:
                raise ImageGenToolError(
                    f"参考图合计体积超过上限 "
                    f"{MAX_REFERENCE_TOTAL_BYTES // (1024 * 1024)}MB，"
                    "请减少张数或压缩后重试"
                )

            filename = path.rsplit("/", 1)[-1]
            mime = resolve_mime(filename, None, data)
            if mime not in REFERENCE_MIME_WHITELIST:
                raise ImageGenToolError(
                    f"参考图 {path} 的格式不受支持（识别为 {mime}），仅支持 "
                    + " / ".join(REFERENCE_MIME_WHITELIST)
                )

            images.append(
                RefImage(
                    index=index,
                    mime_type=mime,
                    base64_data=base64.b64encode(data).decode("ascii"),
                )
            )
        return images

    @staticmethod
    def _validate_reference_path(raw: str) -> str:
        """参考图路径必须是 /workspace 之下的绝对虚拟路径。"""
        try:
            virtual = VirtualPath(raw)
        except Exception as exc:  # noqa: BLE001 - 校验失败统一转文本
            raise ImageGenToolError(
                f"参考图路径必须是合法的绝对虚拟路径（不能包含 '..' / '//'，"
                f"不能是根目录），收到: {raw!r}（{exc}）"
            ) from exc

        value = virtual.value
        if "\\" in value or ":" in value:
            raise ImageGenToolError(f"参考图路径不能包含 '\\' 或 ':'，收到: {raw!r}")
        if not value.startswith(f"{WORKSPACE_ROOT}/"):
            raise ImageGenToolError(
                f"参考图必须位于 {WORKSPACE_ROOT} 之下，收到: {raw!r}"
            )
        return value

    @staticmethod
    def _normalize_resolution(value: Any) -> str:
        """把任意输入归一化为 ``宽x高``；无法识别时回退到默认分辨率。"""
        size = parse_resolution(value) or parse_resolution(DEFAULT_RESOLUTION)
        assert size is not None  # DEFAULT_RESOLUTION 必然合法
        return format_resolution(*size)

    @staticmethod
    def _clamp_wait_timeout(value: Any) -> int:
        if value is None:
            return DEFAULT_WAIT_TIMEOUT
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return DEFAULT_WAIT_TIMEOUT
        return max(0, min(seconds, MAX_WAIT_TIMEOUT))

    def _resolve_oneshot_timeout(self, value: Optional[int]) -> int:
        """一条龙的等待上限：显式入参 > 配置项 > 默认 60 秒。"""
        if value is not None:
            return self._clamp_wait_timeout(value)
        if self._default_wait_timeout > 0:
            return self._clamp_wait_timeout(self._default_wait_timeout)
        return self._clamp_wait_timeout(DEFAULT_ONESHOT_WAIT_TIMEOUT)

    def _pending_result(
        self,
        task_id: str,
        plan: TargetPlan,
        count: int,
        resolution: str,
        timeout: int,
        args: ImageGenerateShowArgs,
        seeds: Optional[List[Dict[str, int]]] = None,
    ) -> Dict[str, Any]:
        """异步模式的结果：给出全部确定路径，交给平台后台下载并在就绪后展示。

        ``paths`` 里的每个条目都会被前端登记成一条待生成文件；``task_id`` /
        ``prefix`` / ``count`` 让后台轮询器能还原同一套确定性命名去取图；
        ``image_generator`` 让轮询器在多配置时用**同一个**配置去下载。

        ``seeds`` 是「index → 种子」的显式关联，写进每条待生成文件子消息，
        这样随机种子在异步落盘、重连、手动补录之后都不会丢。
        """
        predicted = plan.predict(count)
        seed_map = seeds_by_index(seeds)
        return {
            "status": "pending",
            "task_id": task_id,
            "path": predicted[0].path.value,
            "paths": [target.path.value for target in predicted],
            # 显式的「下标 → 路径 → 种子」三元组：登记待生成文件时不依赖列表顺序
            "files": [
                {
                    "index": target.index,
                    "path": target.path.value,
                    "seed": seed_map.get(int(target.index)),
                }
                for target in predicted
            ],
            "count": count,
            "prefix": plan.prefix,
            "resolution": resolution,
            "timeout": timeout,
            "mode": args.mode,
            "seeds": seeds,
            "image_generator": self._generator_name,
            "note": (
                f"图片已提交生成（任务 {task_id}），保存与展示由平台在后台完成，"
                f"最多等待 {timeout} 秒；无需再次调用本工具，也不必调用 "
                "image_download / show。若想确认进度可用 image_task_status。"
            ),
        }

    @staticmethod
    def _require_backend(backend: Optional[BackendProtocol]) -> BackendProtocol:
        if backend is None:
            raise ImageGenToolError(
                "当前会话没有可写的 backend，无法保存图片。请先为该 Agent 挂载一个 Backend。"
            )
        return backend

    async def _status_until_settled(
        self, task_id: str, wait_timeout: int
    ) -> Dict[str, Any]:
        """查询状态；``wait_timeout > 0`` 时短轮询直到任务收敛或超时。

        任务进入 ``completed`` / ``failed`` / ``expired``（或进度达到 100）即提前返回。
        后端自身已实现阻塞时，第一次调用就可能直接返回终态，因此不会额外轮询。
        """
        payload = await self.status(task_id, wait_timeout)
        if wait_timeout <= 0 or self._is_settled(payload):
            return payload

        deadline = time.monotonic() + wait_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(POLL_INTERVAL, remaining))
            payload = await self.status(task_id, 0)
            if self._is_settled(payload):
                break
        return payload

    @classmethod
    def _is_settled(cls, payload: Dict[str, Any]) -> bool:
        status = cls._normalize_status((payload or {}).get("status"))
        if status in ("completed", "failed", "expired"):
            return True
        progress = cls._normalize_progress((payload or {}).get("progress"))
        return progress is not None and progress >= 100

    def _resolve_target(
        self,
        raw_path: str,
        raw_prefix: Optional[str],
    ) -> Tuple[str, str, Optional[str]]:
        """解析目标目录、前缀与（可选）显式扩展名。

        ``path`` 缺失或越界一律报错，绝不静默回退到其它目录；
        ``prefix`` 缺省使用默认值，非法时报错。
        """
        directory, inferred_prefix, ext = self._normalize_dir(raw_path)

        prefix = (raw_prefix or "").strip()
        if not prefix and inferred_prefix:
            prefix = inferred_prefix

        return directory, self._normalize_prefix(prefix), ext

    def _normalize_dir(self, raw_path: str) -> Tuple[str, str, Optional[str]]:
        """返回 ``(目录, 从文件名推断的前缀, 显式扩展名)``，非法输入直接抛错。

        路径合法性交给 :class:`VirtualPath`（绝对路径、拒绝 ``..`` / ``//`` /
        根目录），本方法只在此之上做三件事：

        1. 限定在 ``WORKSPACE_ROOT`` 之下；
        2. 判定「目录」还是「文件名」——**以 ``/`` 结尾即目录**，
           否则末段视为文件名，目录取其父级、末段（去扩展名）作前缀；
        3. 文件名后缀若是常见图片扩展名，则作为**显式扩展名**返回：落盘必须
           沿用它，否则「下载前登记的路径」与「下载后写出的路径」对不上。
        """
        raw = (raw_path or "").strip()
        if not raw:
            raise ImageGenToolError(
                f"image_download 缺少必填参数 path：请指定工作区内的目标目录"
                f"（目录以 / 结尾，例如 {DEFAULT_OUTPUT_DIR}）"
            )

        try:
            virtual = VirtualPath(raw)
        except Exception as exc:  # noqa: BLE001 - 校验失败统一转文本
            raise ImageGenToolError(
                f"path 必须是合法的绝对虚拟路径（不能包含 '..' / '//'，"
                f"不能是根目录），收到: {raw!r}（{exc}）"
            ) from exc

        value = virtual.value
        if "\\" in value or ":" in value:
            raise ImageGenToolError(
                f"path 不能包含 '\\' 或 ':'，收到: {raw!r}"
            )

        # 工作区根自身按目录处理（``/workspace`` 无尾斜杠也不当作文件名）
        if value.rstrip("/") == WORKSPACE_ROOT:
            return WORKSPACE_ROOT, "", None

        if value.endswith("/"):
            directory = value.rstrip("/")
            file_prefix = ""
            ext: Optional[str] = None
        else:
            parent, name = value.rsplit("/", 1)
            directory = parent or WORKSPACE_ROOT
            stem, ext = self._split_ext(name)
            file_prefix = (
                stem if stem and not _FILENAME_FORBIDDEN_RE.search(stem) else ""
            )

        if not (directory == WORKSPACE_ROOT or directory.startswith(f"{WORKSPACE_ROOT}/")):
            raise ImageGenToolError(
                f"path 必须位于 {WORKSPACE_ROOT} 之下，收到: {raw!r}"
            )

        return directory, file_prefix, ext

    @staticmethod
    def _split_ext(name: str) -> Tuple[str, Optional[str]]:
        """拆出 ``(去扩展名的主干, 显式图片扩展名)``。

        只有白名单内的图片后缀才算「显式扩展名」，其余后缀（如 ``a.v2``）
        维持原有行为：整体去后缀当主干，不锁定扩展名。
        """
        if "." not in name:
            return name, None
        stem, suffix = name.rsplit(".", 1)
        ext = f".{suffix}".lower()
        if ext in _IMAGE_EXT_WHITELIST:
            # 统一小写，避免 .JPG / .jpg 登记成两个不同文件名
            return stem, ext
        return stem, None

    def _normalize_prefix(self, raw_prefix: str) -> str:
        prefix = (raw_prefix or "").strip()
        if not prefix:
            return DEFAULT_PREFIX
        if _FILENAME_FORBIDDEN_RE.search(prefix) or len(prefix) > MAX_PREFIX_LEN:
            raise ImageGenToolError(
                "prefix 不能包含 \\ / : * ? \" < > | 及控制字符（长度 1~"
                f"{MAX_PREFIX_LEN}），中文等其它字符均可使用，收到: {prefix!r}"
            )
        return prefix

    def plan_targets(
        self,
        *,
        task_id: str,
        path: str,
        prefix: Optional[str] = None,
        naming: str = NAMING_STAMP,
        multi: Optional[bool] = None,
        ext: Optional[str] = None,
    ) -> TargetPlan:
        """计算落盘路径规划器（纯计算，不联网、不触达 backend）。

        ``path`` 缺失或越界一律报错；``prefix`` 缺省从 path 的文件名推断，
        仍无则用 ``DEFAULT_PREFIX``。``naming=NAMING_TASK`` 时文件名按
        ``task_id`` 确定性生成，可在下载前预测最终路径；此时应同时显式传入
        ``multi`` 与 ``ext``，保证预测与实际落盘的命名判断一致。

        ``ext`` 缺省时从 ``path`` 的文件名后缀推断（如 ``.../凛.jpg`` → ``.jpg``），
        仍无则为 ``None``（``predict`` 兜底 ``DEFAULT_EXT``、``resolve`` 用 blob 的
        真实扩展名）。异步流程必须让两侧一致，否则会「登记 .png 却写出 .jpg」。
        """
        output_dir, resolved_prefix, path_ext = self._resolve_target(path, prefix)
        return TargetPlan(
            task_id=str(task_id or ""),
            output_dir=output_dir,
            prefix=resolved_prefix,
            naming=naming,
            stamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
            ext=(ext or path_ext),
            multi=multi,
        )

    async def download_to(
        self,
        backend: Optional[BackendProtocol],
        task_id: str,
        plan: TargetPlan,
        *,
        index: Optional[int] = None,
        seeds: Optional[Dict[int, int]] = None,
    ) -> DownloadOutcome:
        """按已规划的路径下载并落盘，返回含元信息与原始字节的结果。

        ``seeds`` 是 ``index → 种子`` 映射（来自后端回报），会随每张图一起写进
        ``files``，因此「图 ↔ 种子」的关联不依赖调用方按顺序对齐。
        """
        backend = self._require_backend(backend)

        blobs = await self.download(task_id, index)
        if not blobs:
            raise ImageGenToolError(f"任务 {task_id} 没有可下载的图片")

        payloads: List[Tuple[ImageTarget, bytes]] = [
            (target, self._decode(blob)) for target, blob in plan.resolve(blobs)
        ]
        results = await backend.aupload_files(
            [(target.path, data) for target, data in payloads]
        )

        seed_map: Dict[int, int] = dict(seeds or {})
        for blob in blobs:
            # blob 上带的种子来自实现类的权威记录（任务里逐张存的），优先于状态快照：
            # 中间某张失败时下标会顺移，状态快照里的 index 会错位
            if blob.seed is not None:
                seed_map[int(blob.index)] = int(blob.seed)

        files: List[Dict[str, Any]] = []
        errors: List[str] = []
        items: List[Tuple[ImageTarget, bytes]] = []
        for (target, data), res in zip(payloads, results):
            err = getattr(res, "error", None)
            if err is not None:
                errors.append(f"{target.path.value}: {getattr(err, 'message', err)}")
                continue
            files.append(
                {
                    "index": target.index,
                    "path": target.path.value,
                    "mime": target.mime_type,
                    "bytes": len(data),
                    "seed": seed_map.get(int(target.index)),
                }
            )
            items.append((target, data))

        return DownloadOutcome(files=files, errors=errors, items=items)

    @staticmethod
    def _decode(blob: ImageBlob) -> bytes:
        data = (blob.base64_data or "").strip()
        if not data:
            raise ImageGenToolError(f"第 {blob.index} 张图片数据为空")
        try:
            return base64.b64decode(data, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenToolError(
                f"第 {blob.index} 张图片 base64 数据无法解码: {exc}"
            ) from exc

    _STATUS_ALIASES = {
        "pending": "queued",
        "success": "completed",
        "succeeded": "completed",
        "done": "completed",
        "error": "failed",
        "processing": "running",
        "in_progress": "running",
    }

    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return "unknown"
        return cls._STATUS_ALIASES.get(text, text)

    @staticmethod
    def _normalize_progress(value: Any) -> Optional[int]:
        """把 ``50`` / ``"50%"`` / ``"0.5"`` 统一为 0~100 的整数；无法识别时返回 None。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return max(0, min(int(value), 100))
        text = str(value).strip().rstrip("%").strip()
        if not text:
            return None
        try:
            return max(0, min(int(float(text)), 100))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_task_id(payload: Dict[str, Any]) -> str:
        task_id = (payload or {}).get("task_id")
        if not task_id or not str(task_id).strip():
            raise ImageGenToolError(
                "生图后端未返回 task_id，返回内容不符合标准: "
                + json.dumps(payload, ensure_ascii=False)[:500]
            )
        return str(task_id).strip()

    @staticmethod
    def _dumps(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)
