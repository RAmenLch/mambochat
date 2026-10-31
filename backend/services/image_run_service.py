"""图片重跑（调参重生成）服务。

用户的「重新生成 / 改参数再试一次」走这条独立通道：**不经 LLM、不写对话历史**。
一次重跑只会在消息末尾追加两类子消息，二者都带 ``context_participation_length=0``，
因此永远不参与上下文（KV cache 不受影响）：

1. **生图记录**（``McpTool`` 类型 + ``is_image_run_record``）——记载本次参数与结果，
   前端只在图片区域内以「参数详情」展示，不进正文工具气泡；
2. **FILE 子消息**——本次生成的图片，与原图通过 ``image_slot_id`` 归入同一「插槽」，
   前端据此做左右箭头切换。

失败时只把记录子消息标为失败，**不落 FILE 子消息**（与原工具调用行为一致）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend import schemas
from backend.crud import message_crud
from backend.database import AsyncSessionLocal
from backend.models.base_model import generate_uuid
from backend.schemas import MessageStatus, SubMessageType
from backend.schemas.message import McpToolContent, SubMessageConfig, SubMessageUpdate
from backend.services.file_service import FileService
from backend.services.generation.agent.backend_factory import build_backend_from_chat_id
from backend.services.generation.agent.image_gen.factory import (
    build_image_gen_standard_from_chat_id,
)
from backend.services.generation.agent.image_gen.sink import persist_uploaded
from backend.services.generation.agent.image_gen.standard import (
    DEFAULT_OUTPUT_DIR,
    NAMING_TASK,
    ImageGenerateShowArgs,
)
from backend.services.stream_manager_service import stream_manager

logger = logging.getLogger(__name__)

IMAGE_TOOL_NAME = "image_generate_show"

# 一次重跑最多等待的秒数（含平台侧兜底轮询）
MAX_RERUN_TIMEOUT = 300
# 兜底轮询的单次阻塞时长与轮询间隔
POLL_STATUS_WAIT = 10
POLL_INTERVAL = 2.0

# 同一插槽同时只允许一个重跑在进行：{(message_id, slot_id)}
_inflight: set[Tuple[str, str]] = set()


class ImageRunError(Exception):
    """重跑失败（可直接展示给用户）。"""


class ImageRunConflictError(ImageRunError):
    """同一插槽已有重跑在进行。"""


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------


async def rerun_image_run(
    *,
    sub_message_id: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对某条图片子消息所属的插槽追加一次新的生成。

    Returns
    -------
    ``{"run_id", "slot_id", "status", "record": <SubMessage>, "files": [<SubMessage>],
    "error": <str|null>}``
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}

    async with AsyncSessionLocal() as db:
        source_sub = await message_crud.get_sub_message(db, sub_message_id)
        if source_sub is None:
            raise ImageRunError("找不到目标图片子消息")
        if source_sub.type != SubMessageType.FILE.value:
            raise ImageRunError("只有图片子消息支持重新生成")

        db_message = await message_crud.get_message(db, message_id=source_sub.messageId)
        if db_message is None:
            raise ImageRunError("找不到目标消息")

        message_id = db_message.id
        chat_id = db_message.chatId
        source = _resolve_source(db_message, source_sub)
        if source is None:
            raise ImageRunError("该图片没有可复用的生成参数，无法重新生成")

    run_id = generate_uuid()
    slot_id = source["slot_id"]
    key = (message_id, slot_id)
    if key in _inflight:
        raise ImageRunConflictError("该组图片已有一次生成正在进行，请稍候")
    _inflight.add(key)
    try:
        return await _execute(
            message_id=message_id,
            chat_id=chat_id,
            run_id=run_id,
            slot_id=slot_id,
            source=source,
            overrides=overrides,
        )
    finally:
        _inflight.discard(key)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def _execute(
    *,
    message_id: str,
    chat_id: str,
    run_id: str,
    slot_id: str,
    source: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    merged = _merge_args(source.get("args") or {}, overrides)
    mode = merged.get("mode") or "Normal"
    timeout = _clamp_timeout(merged.get("timeout"))

    args = ImageGenerateShowArgs(
        prompt=merged["prompt"],
        negative_prompt=merged.get("negative_prompt"),
        resolution=merged.get("resolution") or None,
        count=int(merged.get("count") or 1),
        extra=merged.get("extra") or None,
        mode=mode,
        path=merged.get("path") or None,
        timeout=timeout,
    )

    record_id, _ = await _create_record(
        message_id=message_id,
        run_id=run_id,
        slot_id=slot_id,
        args=merged,
        mode=mode,
    )

    try:
        files_meta = await _generate(chat_id=chat_id, args=args, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 失败统一转成记录子消息的失败态
        reason = str(exc) or exc.__class__.__name__
        logger.warning("图片重跑失败(run=%s): %s", run_id, reason)
        payload = await _finish_record(
            message_id=message_id,
            record_id=record_id,
            run_id=run_id,
            args=merged,
            is_error=True,
            result={
                "status": "failed",
                "count": args.count,
                "resolution": args.resolution,
                "mode": mode,
                "files": [],
                "error": reason,
            },
        )
        return {
            "run_id": run_id,
            "slot_id": slot_id,
            "status": "failed",
            "record": payload,
            "files": [],
            "error": reason,
        }

    file_payloads = await _append_file_sub_messages(
        message_id=message_id,
        run_id=run_id,
        slot_id=slot_id,
        files_meta=files_meta,
        args=merged,
        mode=mode,
    )
    payload = await _finish_record(
        message_id=message_id,
        record_id=record_id,
        run_id=run_id,
        args=merged,
        is_error=False,
        result={
            "status": "completed",
            "count": args.count,
            "resolution": args.resolution,
            "mode": mode,
            "files": [
                {
                    "index": item.get("index"),
                    "path": item.get("path"),
                    "mime": item.get("mime"),
                    "file_id": item.get("file_id"),
                }
                for item in files_meta
            ],
        },
    )
    return {
        "run_id": run_id,
        "slot_id": slot_id,
        "status": "completed",
        "record": payload,
        "files": file_payloads,
        "error": None,
    }


async def _generate(
    *,
    chat_id: str,
    args: ImageGenerateShowArgs,
    timeout: int,
) -> List[Dict[str, Any]]:
    """执行一次生成并返回入库后的文件元信息列表。"""
    async with AsyncSessionLocal() as db:
        standard = await build_image_gen_standard_from_chat_id(db, chat_id)
    if standard is None:
        raise ImageRunError("当前会话未启用生图工具或生图服务不可用")

    async with AsyncSessionLocal() as db:
        backend = await build_backend_from_chat_id(db, chat_id)
    if backend is None:
        raise ImageRunError("当前会话没有可写的 backend，无法保存图片")

    raw = await standard.run_generate_show(backend, AsyncSessionLocal, args)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ImageRunError(f"生图服务返回了无法解析的结果: {raw!r}") from None
    if not isinstance(data, dict):
        raise ImageRunError("生图服务返回了无法解析的结果")

    files = data.get("files") or []
    if files:
        return files

    task_id = data.get("task_id")
    if not task_id:
        raise ImageRunError(data.get("error") or "生图任务未返回 task_id")

    # 异步配置 / 同步超时：由平台兜底轮询到收敛后自行下载
    return await _poll_and_collect(
        standard=standard,
        backend=backend,
        task_id=str(task_id),
        args=args,
        timeout=timeout,
    )


async def _poll_and_collect(
    *,
    standard,
    backend,
    task_id: str,
    args: ImageGenerateShowArgs,
    timeout: int,
) -> List[Dict[str, Any]]:
    deadline = asyncio.get_event_loop().time() + timeout
    payload: Dict[str, Any] = {}
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        payload = await standard.status(task_id, min(POLL_STATUS_WAIT, int(remaining) or 1))
        if standard._is_settled(payload):  # noqa: SLF001 - 与工具内部判定保持一致
            break
        await asyncio.sleep(POLL_INTERVAL)

    status = str((payload or {}).get("status") or "").strip().lower()
    if status in ("failed", "expired", "error"):
        raise ImageRunError(
            f"生成任务 {task_id} {status}: {payload.get('error') or '后端未提供失败原因'}"
        )

    plan = standard.plan_targets(
        task_id=task_id,
        path=args.path or DEFAULT_OUTPUT_DIR,
        naming=NAMING_TASK,
        multi=args.count > 1,
    )
    outcome = await standard.download_to(backend, task_id, plan)
    if not outcome.items:
        raise ImageRunError(
            "图片保存失败: "
            + ("; ".join(outcome.errors) if outcome.errors else "生成任务未在预期时间内完成")
        )
    files, errors = await persist_uploaded(AsyncSessionLocal, outcome.items)
    if not files:
        raise ImageRunError("图片入库失败: " + ("; ".join(errors) or "未知原因"))
    return files


# ---------------------------------------------------------------------------
# 源信息解析
# ---------------------------------------------------------------------------


def _config_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _parse_tool_content(sub) -> Optional[McpToolContent]:
    try:
        return McpToolContent.from_json_string(sub.content)
    except (ValueError, TypeError):
        return None


def _tool_result_files(content: McpToolContent) -> List[Dict[str, Any]]:
    """从工具结果里取出文件列表（兼容 ``show`` 的单文件形态）。"""
    if not content.result:
        return []
    try:
        data = json.loads(content.result)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    files = data.get("files")
    if isinstance(files, list):
        return [item for item in files if isinstance(item, dict)]
    file_id = data.get("file_id")
    if isinstance(file_id, str) and file_id:
        return [{"file_id": file_id, "path": None}]
    return []


def _resolve_source(db_message, source_sub) -> Optional[Dict[str, Any]]:
    """确定该图片所属插槽、所属 run 与其可复用的参数。"""
    cfg = _config_dict(getattr(source_sub, "config", None))
    run_id = cfg.get("image_run_id")
    slot_id = cfg.get("image_slot_id") or run_id
    args = cfg.get("image_run_args")

    tool_args: Dict[str, Any] = {}
    files_meta: List[Dict[str, Any]] = []
    if not run_id or not args:
        for sub in getattr(db_message, "sub_messages", []) or []:
            if sub.type != SubMessageType.MCP_TOOL.value:
                continue
            content = _parse_tool_content(sub)
            if content is None:
                continue
            files = _tool_result_files(content)
            hit = any(item.get("file_id") == source_sub.content for item in files)
            if not hit:
                continue
            files_meta = files
            tool_args = content.get_argument_dict()
            if not run_id:
                run_id = content.tool_call_id
                slot_id = slot_id or run_id
            break
    else:
        for sub in getattr(db_message, "sub_messages", []) or []:
            if sub.type != SubMessageType.MCP_TOOL.value:
                continue
            content = _parse_tool_content(sub)
            if content is None or content.tool_call_id != run_id:
                continue
            files_meta = _tool_result_files(content)
            break

    if not run_id:
        return None

    base_args = args if isinstance(args, dict) else tool_args
    if not (base_args or {}).get("prompt"):
        return None

    return {
        "run_id": run_id,
        "slot_id": slot_id or run_id,
        "args": dict(base_args or {}),
        "files_meta": files_meta,
    }


def _merge_args(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """把覆盖参数合并到源参数上，并补出重跑需要的落盘路径。"""
    merged = dict(base or {})
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "extra" and isinstance(value, dict):
            extra = dict(merged.get("extra") or {})
            extra.update(value)
            merged["extra"] = extra
            continue
        merged[key] = value

    if not merged.get("path"):
        directory, prefix = _derive_target(base or {})
        directory = directory.rstrip("/") + "/"
        merged["path"] = f"{directory}{prefix}.png" if prefix else directory
    return merged


def _derive_target(base: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """从源参数里的落盘路径推导目录与文件名前缀，让重跑落在同一目录下。

    规则与工具侧一致：**以 ``/`` 结尾的是目录**，否则末段视为文件名。
    推导失败时回退默认目录，绝不抛错（重跑不能因旧参数形态而失败）。
    """
    try:
        raw = base.get("path")
        if not isinstance(raw, str) or not raw.startswith("/"):
            return DEFAULT_OUTPUT_DIR, None

        if raw.endswith("/"):
            return raw.rstrip("/") or DEFAULT_OUTPUT_DIR, None

        parent, _, name = raw.rpartition("/")
        directory = parent or DEFAULT_OUTPUT_DIR
        stem = name.rsplit(".", 1)[0] if "." in name else name
        return directory, (stem or None)
    except Exception:  # noqa: BLE001 - 推导失败一律回退默认目录
        return DEFAULT_OUTPUT_DIR, None


def _clamp_timeout(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        seconds = 60
    return max(5, min(seconds, MAX_RERUN_TIMEOUT))


# ---------------------------------------------------------------------------
# 子消息落库
# ---------------------------------------------------------------------------


def _sub_payload(db_sub) -> Dict[str, Any]:
    return schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")


async def _create_record(
    *,
    message_id: str,
    run_id: str,
    slot_id: str,
    args: Dict[str, Any],
    mode: str,
) -> Tuple[str, Dict[str, Any]]:
    """落一条「生成记录」子消息（进行中态）。"""
    content = McpToolContent(
        tool_call_id=run_id,
        name=IMAGE_TOOL_NAME,
        arguments=args,
        result=json.dumps(
            {"status": "running", "count": args.get("count") or 1, "files": []},
            ensure_ascii=False,
        ),
    )
    sub_id = generate_uuid()
    async with AsyncSessionLocal() as db:
        db_sub = await message_crud.create_sub_message(
            db,
            message_id=message_id,
            sub_message_data=schemas.message.SubMessageCreate(
                id=sub_id,
                content=content.to_json_string(),
                sortOrder=90,
                type=SubMessageType.MCP_TOOL.value,
                status=MessageStatus.GENERATING,
                config=SubMessageConfig(
                    context_participation_length=0,
                    is_image_run_record=True,
                    image_run_id=run_id,
                    image_slot_id=slot_id,
                    image_run_args=args,
                    show_tool_mode=mode,
                ),
            ),
            sub_message_id=sub_id,
        )
        payload = _sub_payload(db_sub)
    await stream_manager.publish(message_id, {"type": "create", "sub_message": payload})
    return sub_id, payload


async def _finish_record(
    *,
    message_id: str,
    record_id: str,
    run_id: str,
    args: Dict[str, Any],
    is_error: bool,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    content = McpToolContent(
        tool_call_id=run_id,
        name=IMAGE_TOOL_NAME,
        arguments=args,
        result=json.dumps(result, ensure_ascii=False),
        is_error=is_error,
    )
    async with AsyncSessionLocal() as db:
        db_sub = await message_crud.update_sub_message(
            db,
            record_id,
            SubMessageUpdate(
                content=content.to_json_string(),
                status=MessageStatus.FAILED if is_error else MessageStatus.COMPLETED,
            ),
        )
        payload = _sub_payload(db_sub) if db_sub is not None else {}
    await stream_manager.publish(
        message_id,
        {"type": "content_update", "sub_message_id": record_id, "content": content.to_json_string()},
    )
    await stream_manager.publish(
        message_id,
        {
            "type": "status_update",
            "sub_message_id": record_id,
            "status": MessageStatus.FAILED.value if is_error else MessageStatus.COMPLETED.value,
        },
    )
    return payload


async def _append_file_sub_messages(
    *,
    message_id: str,
    run_id: str,
    slot_id: str,
    files_meta: List[Dict[str, Any]],
    args: Dict[str, Any],
    mode: str,
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    async with AsyncSessionLocal() as db:
        file_service = FileService(db)
        for item in files_meta:
            file_id = item.get("file_id")
            if not isinstance(file_id, str) or not file_id:
                continue
            sub_id = generate_uuid()
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=file_id,
                    sortOrder=91,
                    type=SubMessageType.FILE.value,
                    status=MessageStatus.COMPLETED,
                    config=SubMessageConfig(
                        context_participation_length=0,
                        show_tool_mode=mode,
                        image_run_id=run_id,
                        image_slot_id=slot_id,
                        image_run_args=args,
                    ),
                ),
                sub_message_id=sub_id,
            )
            payload = _sub_payload(db_sub)
            record = await file_service.get_file(file_id)
            if record is not None:
                payload["file_info"] = file_service.convert_to_schema(record).model_dump(
                    mode="json"
                )
            payloads.append(payload)
    for payload in payloads:
        await stream_manager.publish(message_id, {"type": "create", "sub_message": payload})
    return payloads


__all__ = [
    "ImageRunError",
    "ImageRunConflictError",
    "rerun_image_run",
]
