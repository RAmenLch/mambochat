"""待生成文件（``show`` / ``image_generate_show`` 落盘等待）的公共处理。

本模块集中两件事：

1. 会话级轮询器用到的原语 —— 定位待生成文件、入库、判失败、驱动异步生图下载；
2. 「手动获取文件」的单条 / 批量入口 —— **超时是正常结果**，这里负责把同一个
   生图任务下所有还没入库的槽位一次性补录，避免 ``count=N`` 的生成只救回第一张、
   其余永久停在失败态。

超时判定、超时配置一律不在此模块调整：它只负责"超时之后怎么合理地把已经生成
好的图取回来"。
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import message_crud
from backend.database import AsyncSessionLocal
from backend.schemas import MessageStatus, SubMessageType
from backend.schemas.enums import FileManagementType
from backend.schemas.message import SubMessageConfig, SubMessageUpdate
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

# 异步生图：同一任务两次驱动下载之间的最小间隔（秒）与最大连续失败次数
IMAGE_DOWNLOAD_RETRY_INTERVAL = 5.0
IMAGE_DOWNLOAD_MAX_ERRORS = 3

# 单次 MCP 状态查询的等待上限（秒）：生图服务的 status 可能长时间阻塞，
# 不设上限会让轮询节流与超时判定彻底失效。
IMAGE_STATUS_CALL_TIMEOUT = 20.0

# 手动「获取文件」接口的整体等待上限（秒）
PENDING_FETCH_TIMEOUT = 30.0

# 正在被手动拉取的子消息（防止重复点击并发执行）
fetch_inflight: set[str] = set()

# 待生成文件失败原因（写入 config.pending_failed_reason）
PENDING_FAIL_REASON_TIMEOUT = "timeout"
PENDING_FAIL_REASON_TASK_FAILED = "task_failed"
PENDING_FAIL_REASON_NO_BACKEND = "no_backend"
PENDING_FAIL_REASON_DOWNLOAD_FAILED = "download_failed"
PENDING_FAIL_REASON_NOT_PRODUCED = "not_produced"

# 会话的「待生成文件」事件订阅队列（由 chat_interaction 的 SSE 端点注册）
chat_subscribers: Dict[str, set[asyncio.Queue]] = {}


async def broadcast_chat_event(chat_id: str, event: dict) -> None:
    queues = chat_subscribers.get(chat_id)
    if not queues:
        return
    for queue in list(queues):
        try:
            queue.put_nowait(event)
        except Exception:
            pass


def config_to_dict(raw) -> dict:
    """把子消息 config 统一成 dict（兼容 ORM 存字符串 / dict / Pydantic 三种形态）。"""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "model_dump"):
        try:
            return raw.model_dump(exclude_none=True)
        except Exception:  # noqa: BLE001 - 兜底，config 解析失败不应中断流程
            return {}
    return {}


async def mark_pending_failed(
    chat_id: str,
    sub_message_id: str,
    path: str,
    reason: str,
) -> None:
    """把待生成文件标记为失败并写入原因。

    ``pending_file_path`` / ``pending_image_task_id`` / 参数快照一律保留，
    前端据此展示失败卡片并提供「获取文件」。
    """
    async with AsyncSessionLocal() as db:
        existing = await message_crud.get_sub_message(db, sub_message_id)
        if existing is not None:
            config = config_to_dict(existing.config)
            config["pending_failed_reason"] = reason
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(
                    status=MessageStatus.FAILED,
                    config=SubMessageConfig(**config),
                ),
            )
    await broadcast_chat_event(chat_id, {
        "type": "file_timeout",
        "sub_message_id": sub_message_id,
        "path": path,
        "reason": reason,
    })


async def process_pending_file(
    backend,
    sub_message_id: str,
    path: str,
) -> dict:
    """下载 → 稳定性校验 → 入库 → 更新子消息。

    ``path`` 必须是**文件真实存在的路径**（发现扩展名漂移时由
    :func:`locate_pending_file` 定位后传入），否则会一直判定为未就绪。

    返回 {"type": "file_ready", "file_id", "file_info"}、
         {"type": "already_ready", "file_id", "file_info"}（已入库过，幂等）、或
         {"type": "still_writing"}（文件未写完，等待下一轮）。

    异步生图槽位（config 带 ``pending_image_task_id``）额外校验内容文件头：
    扩展名是平台按 ``.png`` 兜底拼出来的，不能证明内容就是图片，命中同主干
    的 sidecar 文本时按「未就绪」处理，避免把 JSON 当图片入库展示。
    """
    # 延迟导入：mambo_agents.backends 依赖较重，仅在处理挂起文件时加载
    from mambo_agents.backends.schemas import VirtualPath
    from mambo_agents.backends.protocol import _get_mime_type

    # 幂等：并发/重试场景下该子消息可能已经入库，直接返回既有结果，
    # 避免同一张图被重复写成多条文件记录。
    async with AsyncSessionLocal() as db:
        existing_sub = await message_crud.get_sub_message(db, sub_message_id)
        if (
            existing_sub is not None
            and existing_sub.status == MessageStatus.COMPLETED.value
            and existing_sub.content
        ):
            fs = FileService(db)
            record = await fs.get_file(existing_sub.content)
            return {
                "type": "already_ready",
                "file_id": existing_sub.content,
                "file_info": (
                    fs.convert_to_schema(record).model_dump(mode="json")
                    if record
                    else None
                ),
            }

    pending_task_id = config_to_dict(
        existing_sub.config if existing_sub else None
    ).get("pending_image_task_id")

    r1 = await backend.adownload_files([VirtualPath(path)])
    size1 = len(r1[0].content) if r1 and r1[0].content else 0
    if size1 == 0:
        return {"type": "still_writing"}

    await asyncio.sleep(2)
    r2 = await backend.adownload_files([VirtualPath(path)])
    size2 = len(r2[0].content) if r2 and r2[0].content else 0
    if size1 != size2:
        return {"type": "still_writing"}

    content = r2[0].content
    filename = PurePosixPath(path).name
    from backend.services.generation.agent.image_gen.sink import (
        is_image_bytes,
        resolve_mime,
    )

    mime = resolve_mime(filename, _get_mime_type(path), content)

    if pending_task_id and not is_image_bytes(content):
        logger.warning(
            "待生成文件 %s 的内容不是图片(疑似 %s)，按未就绪处理", path, mime
        )
        return {"type": "still_writing"}

    async with AsyncSessionLocal() as db:
        fs = FileService(db)
        db_file = await fs.save_file_from_bytes(
            data=content or b"",
            filename=filename,
            mime_type=mime,
            management_type=[FileManagementType.SUB_MESSAGE.value],
            sub_path="chat_attachments",
        )

        # 用「读旧 config → 合并」的方式更新，避免 image_slot_id /
        # image_pinned_run_id 等编组字段被覆盖丢失
        existing_sub = await message_crud.get_sub_message(db, sub_message_id)
        config = config_to_dict(existing_sub.config if existing_sub else None)
        config["context_participation_length"] = 0
        for key in (
            "pending_file_path",
            "pending_file_timeout",
            "pending_failed_reason",
            "pending_file_deadline",
            "pending_image_downloaded",
            "pending_image_task_id",
            "pending_image_prefix",
            "pending_image_count",
        ):
            config.pop(key, None)

        await message_crud.update_sub_message(
            db,
            sub_message_id,
            SubMessageUpdate(
                content=db_file.id,
                status=MessageStatus.COMPLETED,
                config=SubMessageConfig(**config),
            ),
        )

        file_schema = fs.convert_to_schema(db_file)
        file_info = file_schema.model_dump(mode='json')

    return {
        "type": "file_ready",
        "file_id": db_file.id,
        "file_info": file_info,
    }


async def glob_pending_files(backend, pattern: str, directory) -> list[str]:
    """在 ``directory`` 下按 pattern 匹配文件，返回虚拟路径字符串列表。"""
    try:
        result = await backend.aglob(pattern, directory)
    except Exception as exc:  # noqa: BLE001 - 列目录失败按「未就绪」处理
        logger.debug("aglob(%s) 失败: %s", pattern, exc)
        return []
    if result is None or result.error is not None:
        return []
    paths: list[str] = []
    for info in result.matches or []:
        if getattr(info, "is_dir", False):
            continue
        try:
            paths.append(info.path.value)
        except AttributeError:  # 兼容直接给字符串的后端
            paths.append(str(info))
    return paths


def _seed_by_path(files: list[dict]) -> dict[str, int]:
    """把下载结果整理成「落盘路径 / 文件名主干 → 种子」的查找表。

    大小双键是有意为之：异步流程登记的是**预测**路径，服务实际写出的扩展名
    可能不同（``x.png`` vs ``x.jpg``），此时按主干仍能对上。
    """
    mapping: dict[str, int] = {}
    for item in files or []:
        if not isinstance(item, dict) or item.get("seed") is None:
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        seed = int(item["seed"])
        mapping[path] = seed
        mapping.setdefault(PurePosixPath(path).stem, seed)
    return mapping


def _seed_of(mapping: dict[str, int], info: dict) -> Optional[int]:
    """取某条待生成文件对应的实际种子（精确路径 → 主干，都没有则 ``None``）。"""
    path = str(info.get("path") or "")
    if not path:
        return None
    if path in mapping:
        return mapping[path]
    return mapping.get(PurePosixPath(path).stem)


async def locate_pending_file(
    backend, path: str, *, loose: bool = True
) -> Optional[str]:
    """定位待生成文件的实际落盘路径。

    先按登记的精确文件名匹配；未命中且 ``loose=True`` 时再按
    「同目录 + 文件名主干 + ``*``」通配。通配只在**异步生图**（``task_id`` 非空）
    时启用：扩展名可能与服务实际产出的格式不一致（登记 ``x.png`` 却写出
    ``x.jpg``），或服务返回张数与预测不同而多了下标后缀——这两种情况文件
    其实已就绪，只认精确名就会一路等到超时。

    普通 ``show`` 等待（无 ``task_id``）不做通配：那里等的是 LLM 自己产出的
    任意文件，按主干匹配容易误吞同前缀的其它文件。

    通配额外受两条**图片类型**约束，防止同主干的 sidecar 文本（生图技能会写出
    与图片同名的 ``.json`` 说明）抢占槽位：

    1. 登记路径必须是图片后缀（``standard._IMAGE_EXT_WHITELIST``），否则不兜底；
    2. 命中项同样必须是图片后缀，非图片候选一律丢弃。
    """
    from mambo_agents.backends.schemas import VirtualPath

    from backend.services.generation.agent.image_gen.standard import ext_from_path

    pp = PurePosixPath(path)
    try:
        directory = VirtualPath(str(pp.parent))
    except Exception:  # noqa: BLE001 - 路径异常时只在工作区根搜
        directory = VirtualPath("/workspace")

    exact = await glob_pending_files(backend, pp.name, directory)
    if exact:
        return exact[0]

    if not loose:
        return None

    stem = pp.stem or pp.name
    if not stem or stem == pp.name or ext_from_path(pp.name) is None:
        return None

    hits = await glob_pending_files(backend, f"{stem}*", directory)
    if not hits:
        return None

    images = [hit for hit in hits if ext_from_path(hit) is not None]
    if not images:
        logger.debug(
            "待生成文件 %s 的通配候选均非图片，忽略: %s",
            path,
            ", ".join(PurePosixPath(hit).name for hit in hits[:5]),
        )
        return None
    # 多图时优先取下标最小的那张（文件名排序即可）
    images.sort()
    logger.info("待生成文件 %s 未见，改用通配命中 %s", path, images[0])
    return images[0]


async def persist_pending_deadline(sub_message_id: str, deadline: float) -> None:
    """把待生成文件的绝对截止时间写进 config。

    轮询器每次重连都会重建内存状态，若截止时间只存在内存里，「60 秒超时」
    会被无限顺延（并且每次都重新下载一遍）。落库后跨实例稳定。
    """
    try:
        async with AsyncSessionLocal() as db:
            existing = await message_crud.get_sub_message(db, sub_message_id)
            if existing is None:
                return
            config = config_to_dict(existing.config)
            if config.get("pending_file_deadline"):
                return
            config["pending_file_deadline"] = float(deadline)
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(config=SubMessageConfig(**config)),
            )
    except Exception as exc:  # noqa: BLE001 - 落库失败只影响重启后的超时精度
        logger.debug("写入待生成文件截止时间失败(sub=%s): %s", sub_message_id, exc)


async def mark_pending_downloaded(sub_message_id: str, seed: Optional[int] = None) -> None:
    """标记「本子消息的图片已下载落盘」，避免轮询器重启后重复下载、重复入库。

    ``seed`` 非空时顺带把这张图实际生效的种子写进 config（随机种子存档）。
    """
    try:
        async with AsyncSessionLocal() as db:
            existing = await message_crud.get_sub_message(db, sub_message_id)
            if existing is None:
                return
            config = config_to_dict(existing.config)
            changed = False
            if not config.get("pending_image_downloaded"):
                config["pending_image_downloaded"] = True
                changed = True
            if seed is not None and config.get("pending_image_seed") != int(seed):
                config["pending_image_seed"] = int(seed)
                changed = True
            if not changed:
                return
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(config=SubMessageConfig(**config)),
            )
    except Exception as exc:  # noqa: BLE001 - 落库失败只影响跨实例去重
        logger.debug("写入已下载标记失败(sub=%s): %s", sub_message_id, exc)


async def mark_pending_seed(sub_message_id: str, seed: Optional[int]) -> None:
    """写入这张图实际生效的种子（未知时跳过），供前端与重跑复用。"""
    if seed is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            existing = await message_crud.get_sub_message(db, sub_message_id)
            if existing is None:
                return
            config = config_to_dict(existing.config)
            if config.get("pending_image_seed") == int(seed):
                return
            config["pending_image_seed"] = int(seed)
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(config=SubMessageConfig(**config)),
            )
    except Exception as exc:  # noqa: BLE001 - 落库失败不影响图片本身
        logger.debug("写入图片种子失败(sub=%s): %s", sub_message_id, exc)


async def scan_chat_pending_sub_messages(
    db: AsyncSession, chat_id: str,
) -> dict[str, dict]:
    """扫描会话下所有等待中的文件子消息。

    返回 ``{sub_message_id: {path, timeout, deadline, downloaded, task_id, prefix,
    count, generator}}``。
    ``task_id`` 非空表示这是异步生图产出：文件还没出现时由轮询器先驱动下载。
    ``generator`` 是产出该图的生图配置名称，多配置时用它还原同一份实现。
    ``deadline`` 是落库的绝对截止时间（epoch 秒），``downloaded`` 表示图已落盘。
    """
    pending: dict[str, dict] = {}
    msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
    for msg in msgs:
        for sub in msg.sub_messages:
            if sub.type != SubMessageType.FILE.value or sub.status != MessageStatus.WAITING.value:
                continue
            raw_cfg = sub.config
            if isinstance(raw_cfg, str):
                try:
                    raw_cfg = json.loads(raw_cfg)
                except json.JSONDecodeError:
                    continue
            if not isinstance(raw_cfg, dict):
                continue
            path = raw_cfg.get("pending_file_path")
            if not path:
                continue
            try:
                deadline = float(raw_cfg.get("pending_file_deadline") or 0) or None
            except (TypeError, ValueError):
                deadline = None
            pending[sub.id] = {
                "path": path,
                "timeout": int(raw_cfg.get("pending_file_timeout") or 300),
                "deadline": deadline,
                "downloaded": bool(raw_cfg.get("pending_image_downloaded")),
                "task_id": raw_cfg.get("pending_image_task_id"),
                "prefix": raw_cfg.get("pending_image_prefix"),
                "count": raw_cfg.get("pending_image_count"),
                "generator": raw_cfg.get("pending_image_generator"),
                "seed": raw_cfg.get("pending_image_seed"),
            }
    return pending


async def drive_task_download(
    standard,
    backend,
    info: dict,
    *,
    wait_timeout: int = 0,
) -> tuple[str, Optional[str], list[dict]]:
    """驱动一次「查状态 → 下载落盘」。

    返回 ``("completed"|"running"|"failed", error, files)``：

    - ``completed``：图片已下载到登记的确定路径，``files`` 是本次落盘的元信息
      （每条带 ``index`` / ``path`` / ``seed``，用于把种子回填到对应子消息）；
    - ``running``：任务尚未收敛（``error`` 为空）或查询/下载暂时失败（``error`` 非空）；
    - ``failed``：任务失败 / 过期 / 无法下载，``error`` 为原因。
    """
    from backend.services.generation.agent.image_gen.standard import (
        NAMING_TASK,
        ext_from_path,
        is_settled,
        seeds_by_index,
        parse_seeds,
    )

    task_id = info.get("task_id")
    if not task_id:
        return "running", None, []

    try:
        payload = await asyncio.wait_for(
            standard.status(task_id, wait_timeout), timeout=IMAGE_STATUS_CALL_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 - 服务暂时不可用，稍后重试
        logger.warning("异步生图查询状态失败(task=%s): %s", task_id, exc)
        return "running", str(exc), []

    status = str((payload or {}).get("status") or "").strip().lower()
    if status in ("failed", "expired", "error"):
        return (
            "failed",
            str((payload or {}).get("error") or f"生成任务 {task_id} 状态为 {status}"),
            [],
        )
    if not is_settled(payload):
        return "running", None, []

    raw_path = str(info.get("path") or "")
    try:
        from mambo_agents.backends.schemas import VirtualPath

        parent = str(PurePosixPath(VirtualPath(raw_path).normalized).parent)
    except Exception:  # noqa: BLE001 - 路径异常时退回字符串截取
        parent = str(PurePosixPath(raw_path).parent)

    try:
        plan = standard.plan_targets(
            task_id=task_id,
            path=parent.rstrip("/") + "/",
            prefix=info.get("prefix"),
            naming=NAMING_TASK,
            multi=bool((info.get("count") or 1) > 1),
            # 必须沿用登记路径的扩展名，否则会写出另一个文件名，
            # 登记路径永远等不到文件（异步流程的核心约束）。
            ext=ext_from_path(raw_path),
        )
        outcome = await standard.download_to(
            backend,
            task_id,
            plan,
            seeds=seeds_by_index(parse_seeds(payload)),
        )
    except Exception as exc:  # noqa: BLE001 - 下载失败下一轮重试
        logger.warning("异步生图下载失败(task=%s): %s", task_id, exc)
        return "running", str(exc), []

    return "completed", None, list(outcome.files or [])


async def drive_pending_image_downloads(
    resolve_standard,
    backend,
    db_pending: dict[str, dict],
    state: dict[str, dict],
) -> dict[str, str]:
    """异步生图：任务收敛后由平台把图片下载到已登记的确定路径。

    同一个 ``task_id`` 在一次轮询里只驱动一次，并以 ``state`` 跨轮节流；
    已下载过（config 里 ``pending_image_downloaded``）的子消息只要文件仍在
    就跳过下载，避免轮询器重连后重复下载、重复入库。

    ``resolve_standard`` 按子消息登记的配置名称返回实现（多配置时一个会话
    可能有多份），返回 ``None`` 表示该配置当前不可用，本轮跳过。
    返回 ``{task_id: 失败原因}``，交给调用方把对应子消息标记为失败。
    """
    failed: dict[str, str] = {}
    for info in db_pending.values():
        task_id = info.get("task_id")
        if not task_id:
            continue

        cursor = state.setdefault(task_id, {"last": 0.0, "done": False, "errors": 0})
        if cursor["done"]:
            continue

        # 已落盘过：文件还在就直接收工，不再重复下载；文件没了则重新取图
        if info.get("downloaded"):
            if await locate_pending_file(backend, info.get("path") or ""):
                cursor["done"] = True
                continue

        now = time.monotonic()
        if now - cursor["last"] < IMAGE_DOWNLOAD_RETRY_INTERVAL:
            continue
        cursor["last"] = now

        standard = await resolve_standard(info.get("generator"))
        if standard is None:
            continue

        outcome, error, files = await drive_task_download(standard, backend, info)
        if outcome == "completed":
            cursor["done"] = True
            seed_by_path = _seed_by_path(files)
            # 同一个 task_id 可能对应多条子消息（一次生成多张），全部打上已下载标记
            for other_id, other in db_pending.items():
                if other.get("task_id") == task_id:
                    await mark_pending_downloaded(
                        other_id, seed=_seed_of(seed_by_path, other)
                    )
            continue
        if outcome == "failed":
            cursor["done"] = True
            failed[task_id] = error or "生成任务失败"
            continue
        if error is None:
            # 任务还在生成中，正常等待下一轮
            continue
        cursor["errors"] += 1
        if cursor["errors"] >= IMAGE_DOWNLOAD_MAX_ERRORS:
            cursor["done"] = True

    return failed


# ----------------------------------------------------------------------
# 手动获取（单条 / 批量）
#
# 异步生图任务可能远慢于登记的等待上限：槽位被判 timeout 之后，图仍会陆续落盘。
# 这里把「同一个 task 下所有还没入库的槽位」合并成一次获取：只驱动一次下载，
# 再逐条入库并各自广播，所以一次点击就能补齐 count=N 的全部图片。
# ----------------------------------------------------------------------

# 同一 task 的下载互斥（run 内多个槽位 / 用户连点）
_task_fetch_locks: Dict[str, asyncio.Lock] = {}


@dataclass
class PendingFetchItem:
    """单条待生成文件的获取结果。"""

    sub_message_id: str
    #: completed=已入库 / running=仍在生成或文件未写完 / failed=任务或下载失败
    status: str
    file_id: Optional[str] = None
    file_info: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class _PendingSlot:
    """待补录槽位（从待生成文件子消息的 config 还原）。"""

    sub_id: str
    chat_id: str
    path: str
    task_id: Optional[str]
    prefix: Optional[str]
    count: Optional[int]
    generator: Optional[str]

    def task_info(self) -> Dict[str, Any]:
        """还原驱动下载所需的 task 信息（与轮询器同形）。"""
        return {
            "task_id": self.task_id,
            "path": self.path,
            "prefix": self.prefix,
            "count": self.count,
            "generator": self.generator,
        }


def _task_lock(task_id: str) -> asyncio.Lock:
    return _task_fetch_locks.setdefault(task_id, asyncio.Lock())


async def _completed_item(db, sub, file_id: str) -> PendingFetchItem:
    """已入库槽位的返回结果（顺带刷新 file_info）。"""
    fs = FileService(db)
    record = await fs.get_file(file_id)
    return PendingFetchItem(
        sub.id,
        "completed",
        file_id=file_id,
        file_info=(
            fs.convert_to_schema(record).model_dump(mode="json") if record else None
        ),
    )


async def _load_slots(
    sub_message_ids: List[str],
) -> tuple[List[_PendingSlot], Dict[str, PendingFetchItem]]:
    """读取子消息，拆成「待补录槽位」与「可直接返回的结果」。

    已入库的槽位直接返回完成结果；不是待生成文件的子消息返回失败原因；
    ``waiting`` 与 ``failed`` 一律进入待补录列表（failed 正是需要被救回的对象）。
    """
    slots: List[_PendingSlot] = []
    done: Dict[str, PendingFetchItem] = {}
    async with AsyncSessionLocal() as db:
        for sub_id in sub_message_ids:
            sub = await message_crud.get_sub_message(db, sub_id)
            if sub is None or sub.type != SubMessageType.FILE.value:
                done[sub_id] = PendingFetchItem(
                    sub_id, "failed", error="找不到该文件子消息"
                )
                continue

            if sub.status == MessageStatus.COMPLETED.value and sub.content:
                done[sub_id] = await _completed_item(db, sub, sub.content)
                continue

            config = config_to_dict(sub.config)
            path = config.get("pending_file_path")
            if not path:
                done[sub_id] = PendingFetchItem(
                    sub_id, "failed", error="该子消息不是待生成文件"
                )
                continue

            db_message = await message_crud.get_message(db, message_id=sub.messageId)
            if db_message is None:
                done[sub_id] = PendingFetchItem(
                    sub_id, "failed", error="找不到所属会话"
                )
                continue

            try:
                count = int(config.get("pending_image_count") or 0) or None
            except (TypeError, ValueError):
                count = None

            slots.append(
                _PendingSlot(
                    sub_id=sub_id,
                    chat_id=db_message.chatId,
                    path=path,
                    task_id=config.get("pending_image_task_id"),
                    prefix=config.get("pending_image_prefix"),
                    count=count,
                    generator=config.get("pending_image_generator"),
                )
            )
    return slots, done


async def _build_backend(chat_id: str):
    from backend.services.generation.agent.backend_factory import (
        build_backend_from_chat_id,
    )

    async with AsyncSessionLocal() as db:
        return await build_backend_from_chat_id(db, chat_id)


async def _resolve_standard(chat_id: str, generator: Optional[str]):
    from backend.services.generation.agent.image_gen.factory import (
        build_image_gen_standard_from_chat_id,
    )

    async with AsyncSessionLocal() as db:
        return await build_image_gen_standard_from_chat_id(
            db, chat_id, generator=generator
        )


async def _persist_slot(
    chat_id: str,
    backend,
    slot: _PendingSlot,
    path: str,
    items: Dict[str, PendingFetchItem],
) -> None:
    """把一条槽位入库并广播；单条失败不影响同批其它槽位。"""
    try:
        result = await asyncio.wait_for(
            process_pending_file(backend, slot.sub_id, path),
            timeout=PENDING_FETCH_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 单张失败统一转失败态
        logger.warning(
            "获取待生成文件失败(sub=%s): %s", slot.sub_id, exc, exc_info=True
        )
        await mark_pending_failed(
            chat_id, slot.sub_id, slot.path, PENDING_FAIL_REASON_DOWNLOAD_FAILED
        )
        items[slot.sub_id] = PendingFetchItem(
            slot.sub_id,
            "failed",
            error=str(exc) or PENDING_FAIL_REASON_DOWNLOAD_FAILED,
        )
        return

    if result["type"] == "still_writing":
        items[slot.sub_id] = PendingFetchItem(
            slot.sub_id, "running", error="文件尚未写完，请稍后再试"
        )
        return

    items[slot.sub_id] = PendingFetchItem(
        slot.sub_id,
        "completed",
        file_id=result.get("file_id"),
        file_info=result.get("file_info"),
    )
    if result["type"] == "file_ready":
        await broadcast_chat_event(
            chat_id,
            {
                "type": "file_ready",
                "sub_message_id": slot.sub_id,
                "file_id": result.get("file_id"),
                "file_info": result.get("file_info"),
            },
        )


async def _fetch_task_group(
    chat_id: str,
    backend,
    group: List[_PendingSlot],
    items: Dict[str, PendingFetchItem],
) -> None:
    """同一 task 下的多个槽位：驱动一次下载，再逐条入库。"""
    info = group[0].task_info()
    seed_by_path: dict[str, int] = {}
    async with _task_lock(str(info["task_id"])):
        located: Dict[str, str] = {}
        for slot in group:
            hit = await locate_pending_file(backend, slot.path, loose=True)
            if hit:
                located[slot.sub_id] = hit

        missing = [slot for slot in group if slot.sub_id not in located]
        if missing:
            standard = await _resolve_standard(chat_id, info.get("generator"))
            if standard is None:
                for slot in missing:
                    await mark_pending_failed(
                        chat_id, slot.sub_id, slot.path, PENDING_FAIL_REASON_NO_BACKEND
                    )
                    items[slot.sub_id] = PendingFetchItem(
                        slot.sub_id, "failed", error="生图配置不可用，无法获取文件"
                    )
                missing = []
            else:
                try:
                    outcome, error, files = await asyncio.wait_for(
                        drive_task_download(standard, backend, info),
                        timeout=PENDING_FETCH_TIMEOUT,
                    )
                    seed_by_path = _seed_by_path(files)
                except asyncio.TimeoutError:
                    outcome, error = "running", "获取文件超时，请稍后重试"

                if outcome == "failed":
                    for slot in missing:
                        await mark_pending_failed(
                            chat_id,
                            slot.sub_id,
                            slot.path,
                            PENDING_FAIL_REASON_TASK_FAILED,
                        )
                        items[slot.sub_id] = PendingFetchItem(
                            slot.sub_id, "failed", error=error or "生成任务失败"
                        )
                    missing = []
                elif outcome == "running":
                    for slot in missing:
                        items[slot.sub_id] = PendingFetchItem(
                            slot.sub_id,
                            "running",
                            error=error or "任务仍在生成中，请稍后再试",
                        )
                    missing = []
                else:
                    # 下载完成：逐个复核落盘结果，缺失的说明服务实际出图少于请求张数
                    for slot in missing:
                        hit = await locate_pending_file(backend, slot.path, loose=True)
                        if hit:
                            located[slot.sub_id] = hit
                            continue
                        await mark_pending_failed(
                            chat_id,
                            slot.sub_id,
                            slot.path,
                            PENDING_FAIL_REASON_NOT_PRODUCED,
                        )
                        items[slot.sub_id] = PendingFetchItem(
                            slot.sub_id,
                            "failed",
                            error=PENDING_FAIL_REASON_NOT_PRODUCED,
                        )
                    missing = []

        for slot in group:
            path = located.get(slot.sub_id)
            if path:
                await mark_pending_seed(
                    slot.sub_id, _seed_of(seed_by_path, {"path": path}) or _seed_of(
                        seed_by_path, {"path": slot.path}
                    )
                )
                await _persist_slot(chat_id, backend, slot, path, items)


async def fetch_pending_files(sub_message_ids: List[str]) -> List[PendingFetchItem]:
    """批量获取待生成文件（同一 task 只驱动一次下载，再逐条入库）。

    返回条目顺序与 ``sub_message_ids`` 一致；无法识别的 id 不会出现在结果里。
    正在被其它请求获取的槽位返回 ``running``，不阻塞整批。
    """
    ordered = list(
        dict.fromkeys(i for i in sub_message_ids if isinstance(i, str) and i)
    )
    if not ordered:
        return []

    slots, items = await _load_slots(ordered)

    runnable: List[_PendingSlot] = []
    for slot in slots:
        if slot.sub_id in fetch_inflight:
            items[slot.sub_id] = PendingFetchItem(
                slot.sub_id, "running", error="正在获取中，请稍候"
            )
            continue
        runnable.append(slot)

    by_chat: Dict[str, List[_PendingSlot]] = {}
    for slot in runnable:
        by_chat.setdefault(slot.chat_id, []).append(slot)

    for chat_id, chat_slots in by_chat.items():
        for slot in chat_slots:
            fetch_inflight.add(slot.sub_id)
        backend = None
        try:
            backend = await _build_backend(chat_id)
            if backend is None:
                for slot in chat_slots:
                    await mark_pending_failed(
                        chat_id, slot.sub_id, slot.path, PENDING_FAIL_REASON_NO_BACKEND
                    )
                    items[slot.sub_id] = PendingFetchItem(
                        slot.sub_id,
                        "failed",
                        error="当前会话没有可用的 backend，无法获取文件",
                    )
                continue

            by_task: Dict[str, List[_PendingSlot]] = {}
            singles: List[_PendingSlot] = []
            for slot in chat_slots:
                if slot.task_id:
                    by_task.setdefault(str(slot.task_id), []).append(slot)
                else:
                    singles.append(slot)

            for task_slots in by_task.values():
                await _fetch_task_group(chat_id, backend, task_slots, items)

            for slot in singles:
                path = (
                    await locate_pending_file(backend, slot.path, loose=False)
                    or slot.path
                )
                await _persist_slot(chat_id, backend, slot, path, items)
        except Exception as exc:  # noqa: BLE001 - 单个会话失败不拖累其余会话
            logger.warning(
                "批量获取待生成文件失败(chat=%s): %s", chat_id, exc, exc_info=True
            )
            for slot in chat_slots:
                items.setdefault(
                    slot.sub_id,
                    PendingFetchItem(
                        slot.sub_id, "failed", error=str(exc) or "获取文件失败"
                    ),
                )
        finally:
            for slot in chat_slots:
                fetch_inflight.discard(slot.sub_id)
            if backend is not None and hasattr(backend, "aclose"):
                try:
                    await backend.aclose()
                except Exception:  # noqa: BLE001 - 关闭失败不影响结果
                    pass

    return [items[i] for i in ordered if i in items]
