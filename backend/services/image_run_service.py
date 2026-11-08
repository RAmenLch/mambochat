"""图片重跑（调参重生成）服务。

用户的「重新生成 / 改参数再试一次」走这条独立通道：**不经 LLM、不写对话历史**。
一次重跑只会在消息末尾追加两类子消息，二者都带 ``context_participation_length=0``，
因此永远不参与上下文（KV cache 不受影响）：

1. **生图记录**（``McpTool`` 类型 + ``is_image_run_record``）——记载本次参数与结果，
   前端只在图片区域内以「参数详情」展示，不进正文工具气泡；
2. **FILE 子消息**——本次生成的图片，与原图通过 ``image_slot_id`` 归入同一「插槽」，
   前端据此做左右箭头切换。

重跑与 agent 异步生图**行为一致**：提交成功即落 N 条「待生成文件」子消息
（``status=waiting`` + ``pending_image_task_id``），落盘 / 入库由会话级轮询器完成，
超时后由轮询器写 ``pending_failed_reason`` 并提供「获取文件」。请求线程只负责
提交，绝不自行下载（否则会和轮询器重复取图）。只有提交阶段就失败时，才只把记录
子消息标为失败、不落 FILE 子消息。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend import schemas
from backend.crud import message_crud
from backend.database import AsyncSessionLocal
from backend.models.base_model import generate_uuid
from backend.schemas import MessageStatus, SubMessageType
from backend.schemas.message import McpToolContent, SubMessageConfig, SubMessageUpdate
from backend.services.generation.agent.backend_factory import build_backend_from_chat_id
from backend.services.generation.agent.image_gen.factory import (
    build_image_gen_standard_from_chat_id,
)
from backend.services.generation.agent.image_gen.standard import (
    DEFAULT_OUTPUT_DIR,
    generate_show_args_model,
)
from backend.services.stream_manager_service import stream_manager

logger = logging.getLogger(__name__)

IMAGE_TOOL_NAME = "image_generate_show"

# 一次重跑的后台等待上限（秒）；不传 timeout 时由标准框架按配置/默认值解析
MAX_RERUN_TIMEOUT = 300

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

    ``status`` 为 ``pending``（已提交，落盘由后台轮询器完成）/ ``failed``
    （仅提交阶段失败）。
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

    args = generate_show_args_model(True)(
        prompt=merged["prompt"],
        image_generator=merged.get("image_generator") or None,
        negative_prompt=merged.get("negative_prompt"),
        resolution=merged.get("resolution") or None,
        count=int(merged.get("count") or 1),
        extra=merged.get("extra") or None,
        mode=mode,
        path=merged.get("path") or None,
        timeout=_clamp_timeout(merged.get("timeout")),
        reference_images=merged.get("reference_images") or None,
    )

    backend = await _require_backend(chat_id)

    try:
        return await _submit_and_record(
            message_id=message_id,
            chat_id=chat_id,
            run_id=run_id,
            slot_id=slot_id,
            args=args,
            merged=merged,
            mode=mode,
            backend=backend,
        )
    finally:
        await _close_backend(backend)


async def _submit_and_record(
    *,
    message_id: str,
    chat_id: str,
    run_id: str,
    slot_id: str,
    args: Any,
    merged: Dict[str, Any],
    mode: str,
    backend: Any,
) -> Dict[str, Any]:
    record_id, _ = await _create_record(
        message_id=message_id,
        run_id=run_id,
        slot_id=slot_id,
        args=merged,
        mode=mode,
    )

    try:
        pending = await _submit(chat_id=chat_id, args=args, backend=backend)
    except Exception as exc:  # noqa: BLE001 - 提交失败统一转成记录子消息的失败态
        reason = str(exc) or exc.__class__.__name__
        logger.warning("图片重跑提交失败(run=%s): %s", run_id, reason)
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

    timeout = int(pending.get("timeout") or 0)
    file_payloads = await _append_pending_file_sub_messages(
        message_id=message_id,
        run_id=run_id,
        slot_id=slot_id,
        pending=pending,
        args=merged,
        mode=mode,
        timeout=timeout,
    )
    payload = await _finish_record(
        message_id=message_id,
        record_id=record_id,
        run_id=run_id,
        args=merged,
        is_error=False,
        result={
            "status": "pending",
            "task_id": pending.get("task_id"),
            "count": pending.get("count") or args.count,
            "resolution": pending.get("resolution") or args.resolution,
            "mode": mode,
            "timeout": timeout,
            "files": [],
        },
    )
    _start_pending_poller(chat_id)
    return {
        "run_id": run_id,
        "slot_id": slot_id,
        "status": "pending",
        "record": payload,
        "files": file_payloads,
        "error": None,
    }


async def _require_backend(chat_id: str):
    """重跑本身不落盘，但下载由后台轮询器完成，缺 backend 时尽早给出明确错误。

    返回的 backend 同时用于读取参考图（``reference_images``）。
    """
    async with AsyncSessionLocal() as db:
        backend = await build_backend_from_chat_id(db, chat_id)
    if backend is None:
        raise ImageRunError("当前会话没有可写的 backend，无法保存图片")
    return backend


async def _close_backend(backend) -> None:
    aclose = getattr(backend, "aclose", None)
    if aclose is not None:
        try:
            await aclose()
        except Exception:  # noqa: BLE001 - 探测型 backend 关闭失败不影响重跑
            pass


async def _submit(
    *,
    chat_id: str,
    args: Any,
    backend: Any,
) -> Dict[str, Any]:
    """只提交生成任务，返回「待生成」描述（``task_id`` + 全部确定路径）。"""
    async with AsyncSessionLocal() as db:
        standard = await build_image_gen_standard_from_chat_id(
            db, chat_id, generator=getattr(args, "image_generator", None)
        )
    if standard is None:
        raise ImageRunError("当前会话未启用生图工具或生图服务不可用")

    raw = await standard.run_pending(backend, args)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ImageRunError(f"生图服务返回了无法解析的结果: {raw!r}") from None
    if not isinstance(data, dict):
        raise ImageRunError("生图服务返回了无法解析的结果")
    if not data.get("task_id"):
        raise ImageRunError(data.get("error") or "生图任务未返回 task_id")
    return data


def _start_pending_poller(chat_id: str) -> None:
    """立刻启动会话级待生成文件轮询器。

    前端进入会话时也会通过 SSE 启动同一个任务；这里主动启动是为了让重跑
    不依赖页面是否还停留在该会话上（轮询任务与客户端连接无关）。
    """
    from backend.routers.chat_interaction import (
        _chat_pending_tasks,
        _poll_chat_pending_files,
    )

    existing = _chat_pending_tasks.get(chat_id)
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(_poll_chat_pending_files(chat_id))
    _chat_pending_tasks[chat_id] = task
    task.add_done_callback(lambda _: _chat_pending_tasks.pop(chat_id, None))


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


def _clamp_timeout(value: Any) -> Optional[int]:
    """重跑的等待窗口：不传时返回 ``None``，交给标准框架按配置/默认值解析。

    这样重跑与 agent 侧 ``image_generate_show`` 的等待时长完全同源
    （``_resolve_oneshot_timeout``），不会出现两个入口窗口不一致。
    """
    if value is None or value == "":
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
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


async def _append_pending_file_sub_messages(
    *,
    message_id: str,
    run_id: str,
    slot_id: str,
    pending: Dict[str, Any],
    args: Dict[str, Any],
    mode: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    """落 N 条「待生成文件」子消息，形态与 agent 异步生图完全一致。

    路径按 ``task_id`` 确定性命名提前预测；后台轮询器据 ``pending_image_task_id``
    驱动下载，就绪后把子消息就地改成完成态，超时则写 ``pending_failed_reason``
    并提供「获取文件」。子消息一律 ``context_participation_length=0``，不进入上下文。
    """
    paths = pending.get("paths") or ([pending["path"]] if pending.get("path") else [])
    payloads: List[Dict[str, Any]] = []
    async with AsyncSessionLocal() as db:
        for path in paths:
            sub_id = generate_uuid()
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content="",
                    sortOrder=91,
                    type=SubMessageType.FILE.value,
                    status=MessageStatus.WAITING,
                    config=SubMessageConfig(
                        context_participation_length=0,
                        show_tool_mode=mode,
                        image_run_id=run_id,
                        image_slot_id=slot_id,
                        image_run_args=args,
                        pending_file_path=path,
                        show_file_path=path,
                        pending_file_timeout=timeout,
                        pending_file_deadline=time.time() + float(timeout or 300),
                        pending_image_task_id=pending.get("task_id"),
                        pending_image_prefix=pending.get("prefix"),
                        pending_image_count=pending.get("count"),
                        pending_image_generator=pending.get("image_generator"),
                    ),
                ),
                sub_message_id=sub_id,
            )
            payloads.append(_sub_payload(db_sub))
    for payload in payloads:
        await stream_manager.publish(message_id, {"type": "create", "sub_message": payload})
    return payloads


__all__ = [
    "ImageRunError",
    "ImageRunConflictError",
    "rerun_image_run",
]
