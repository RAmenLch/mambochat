# backend/routers/chat_interaction.py

import asyncio
import json
import logging
import time
from pathlib import PurePosixPath

from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from typing import List, Optional

from backend.services import generation_service
from backend.services import chat_status_service
from backend.services.stream_manager_service import stream_manager
from backend.services.file_service import FileService
from backend.services import maintenance
from backend.services.group_chat import service as group_service
from backend.services.group_chat import generation_bridge
from backend.crud import chat_crud, message_crud, setting_crud
from backend import schemas
from backend.models import chat_model
from backend.database import get_db, AsyncSessionLocal
from backend.routers.chat_management import _apply_default_model_to_chat_object
from backend.exceptions import AppHTTPException
from backend.schemas import SubMessageType, MessageStatus
from backend.schemas.message import ToolApprovalRequest, SubMessageConfig, SubMessageUpdate
from backend.schemas.enums import FileManagementType, GroupTaskKind

from pydantic import BaseModel

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
_fetch_inflight: set[str] = set()

# 待生成文件失败原因（写入 config.pending_failed_reason）
PENDING_FAIL_REASON_TIMEOUT = "timeout"
PENDING_FAIL_REASON_TASK_FAILED = "task_failed"
PENDING_FAIL_REASON_NO_BACKEND = "no_backend"
PENDING_FAIL_REASON_DOWNLOAD_FAILED = "download_failed"

class TaskStatusRequest(BaseModel):
    task_ids: List[str]

class TaskStatusResponse(BaseModel):
    running_tasks: List[str]


class AskUserAnswerRequest(BaseModel):
    sub_message_id: str
    answers: List[str]
    ask_status: str = "answered"


class ImageRunRerunRequest(BaseModel):
    """图片重跑参数：留空的字段沿用该插槽上一次生成的取值。"""

    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    resolution: Optional[str] = None
    count: Optional[int] = None
    mode: Optional[str] = None
    extra: Optional[dict] = None
    path: Optional[str] = None
    timeout: Optional[int] = None


class PendingFileFetchResponse(BaseModel):
    """手动获取待生成文件的结果。

    - ``completed``：已下载并入库，附 ``file_id`` / ``file_info``；
    - ``running``：任务仍在生成或文件尚未写完，稍后可再次点击；
    - ``failed``：任务失败 / 下载失败，``error`` 为原因。
    """

    status: str
    file_id: Optional[str] = None
    file_info: Optional[dict] = None
    error: Optional[str] = None


# ----------------------------------------------------------------------
# Pending file (show wait) — 按会话聚合
# 同一会话的所有待生成文件共享一个轮询任务与一个 backend 实例。
# 任务生命周期：由首个 wait-for-files 连接启动，所有 pending 文件达到
# 终态（成功入库 / 超时失败）后结束；客户端断开不影响任务继续运行。
# ----------------------------------------------------------------------

_chat_pending_tasks: dict[str, asyncio.Task] = {}
_chat_subscribers: dict[str, set[asyncio.Queue]] = {}


async def _broadcast_chat_event(chat_id: str, event: dict) -> None:
    queues = _chat_subscribers.get(chat_id)
    if not queues:
        return
    for queue in list(queues):
        try:
            queue.put_nowait(event)
        except Exception:
            pass


def _config_to_dict(raw) -> dict:
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


async def _mark_pending_failed(
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
            config = _config_to_dict(existing.config)
            config["pending_failed_reason"] = reason
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(
                    status=MessageStatus.FAILED,
                    config=SubMessageConfig(**config),
                ),
            )
    await _broadcast_chat_event(chat_id, {
        "type": "file_timeout",
        "sub_message_id": sub_message_id,
        "path": path,
        "reason": reason,
    })


async def _process_pending_file(
    backend,
    sub_message_id: str,
    path: str,
) -> dict:
    """下载 → 稳定性校验 → 入库 → 更新子消息。

    返回 {"type": "file_ready", "file_id", "file_info"} 或
         {"type": "still_writing"}（文件未写完，等待下一轮）。
    """
    # 延迟导入：mambo_agents.backends 依赖较重，仅在处理挂起文件时加载
    from mambo_agents.backends.schemas import VirtualPath
    from mambo_agents.backends.protocol import _get_mime_type

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
    from backend.services.generation.agent.image_gen.sink import resolve_mime

    mime = resolve_mime(filename, _get_mime_type(path), content)

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
        config = _config_to_dict(existing_sub.config if existing_sub else None)
        config["context_participation_length"] = 0
        for key in ("pending_file_path", "pending_file_timeout", "pending_failed_reason"):
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


async def _scan_chat_pending_sub_messages(
    db: AsyncSession, chat_id: str,
) -> dict[str, dict]:
    """扫描会话下所有等待中的文件子消息。

    返回 ``{sub_message_id: {path, timeout, task_id, prefix, count}}``。
    ``task_id`` 非空表示这是异步生图产出：文件还没出现时由轮询器先驱动下载。
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
            pending[sub.id] = {
                "path": path,
                "timeout": int(raw_cfg.get("pending_file_timeout") or 300),
                "task_id": raw_cfg.get("pending_image_task_id"),
                "prefix": raw_cfg.get("pending_image_prefix"),
                "count": raw_cfg.get("pending_image_count"),
            }
    return pending


async def _drive_task_download(
    standard,
    backend,
    info: dict,
    *,
    wait_timeout: int = 0,
) -> tuple[str, Optional[str]]:
    """驱动一次「查状态 → 下载落盘」。

    返回 ``("completed"|"running"|"failed", error)``：

    - ``completed``：图片已下载到登记的确定路径；
    - ``running``：任务尚未收敛（``error`` 为空）或查询/下载暂时失败（``error`` 非空）；
    - ``failed``：任务失败 / 过期 / 无法下载，``error`` 为原因。
    """
    from backend.services.generation.agent.image_gen.standard import (
        NAMING_TASK,
        is_settled,
    )

    task_id = info.get("task_id")
    if not task_id:
        return "running", None

    try:
        payload = await asyncio.wait_for(
            standard.status(task_id, wait_timeout), timeout=IMAGE_STATUS_CALL_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 - 服务暂时不可用，稍后重试
        logger.warning("异步生图查询状态失败(task=%s): %s", task_id, exc)
        return "running", str(exc)

    status = str((payload or {}).get("status") or "").strip().lower()
    if status in ("failed", "expired", "error"):
        return "failed", str(
            (payload or {}).get("error") or f"生成任务 {task_id} 状态为 {status}"
        )
    if not is_settled(payload):
        return "running", None

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
        )
        await standard.download_to(backend, task_id, plan)
    except Exception as exc:  # noqa: BLE001 - 下载失败下一轮重试
        logger.warning("异步生图下载失败(task=%s): %s", task_id, exc)
        return "running", str(exc)

    return "completed", None


async def _drive_pending_image_downloads(
    standard,
    backend,
    db_pending: dict[str, dict],
    state: dict[str, dict],
) -> dict[str, str]:
    """异步生图：任务收敛后由平台把图片下载到已登记的确定路径。

    同一个 ``task_id`` 在一次轮询里只驱动一次，并以 ``state`` 跨轮节流；
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
        now = time.monotonic()
        if now - cursor["last"] < IMAGE_DOWNLOAD_RETRY_INTERVAL:
            continue
        cursor["last"] = now

        outcome, error = await _drive_task_download(standard, backend, info)
        if outcome == "completed":
            cursor["done"] = True
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


async def _poll_chat_pending_files(chat_id: str) -> None:
    """轮询会话下所有待生成文件，就绪/超时后入库并广播事件。"""
    from backend.services.generation.agent.backend_factory import (
        build_backend_from_chat_id,
    )
    from backend.services.generation.agent.image_gen.factory import (
        build_image_gen_standard_from_chat_id,
    )
    # 延迟导入：mambo_agents.backends 依赖较重
    from mambo_agents.backends.schemas import VirtualPath

    backend = None
    try:
        async with AsyncSessionLocal() as db:
            backend = await build_backend_from_chat_id(db, chat_id)

        # sub_message_id -> {path, timeout, task_id, prefix, count, deadline}
        pending: dict[str, dict] = {}
        # task_id -> {last, done, errors}：异步生图下载的节流状态
        image_state: dict[str, dict] = {}
        image_standard = None

        while True:
            # 1. 与 DB 同步 pending 集合（新文件自动纳入，已终态移除）
            async with AsyncSessionLocal() as db:
                db_pending = await _scan_chat_pending_sub_messages(db, chat_id)

            now = time.monotonic()
            for sub_id in list(pending.keys()):
                if sub_id not in db_pending:
                    del pending[sub_id]
            for sub_id, info in db_pending.items():
                if sub_id not in pending:
                    pending[sub_id] = {**info, "deadline": now + info["timeout"]}

            if not pending:
                break

            # 2. 异步生图：任务收敛后先把图下载到确定路径（文件出现由下一步接管）
            if any(item["task_id"] for item in db_pending.values()):
                if image_standard is None:
                    async with AsyncSessionLocal() as db:
                        image_standard = await build_image_gen_standard_from_chat_id(
                            db, chat_id
                        )
                if image_standard is not None:
                    failed_tasks = await _drive_pending_image_downloads(
                        image_standard, backend, db_pending, image_state
                    )
                    for item in pending.values():
                        reason = failed_tasks.get(item["task_id"])
                        if reason is not None:
                            item["deadline"] = 0.0
                            item["fail_reason"] = PENDING_FAIL_REASON_TASK_FAILED
                            item["fail_error"] = reason

            # 3. 逐个处理：先判文件是否就绪，未就绪再判是否超时
            for sub_id, item in list(pending.items()):
                if sub_id in _fetch_inflight:
                    continue

                path = item["path"]

                file_appeared = False
                try:
                    pp = PurePosixPath(path)
                    glob_result = await backend.aglob(pp.name, VirtualPath(str(pp.parent)))
                    file_appeared = glob_result.error is None and bool(glob_result.matches)
                except Exception:
                    file_appeared = False

                if file_appeared:
                    result = await _process_pending_file(backend, sub_id, path)
                    if result["type"] == "file_ready":
                        await _broadcast_chat_event(chat_id, {
                            "type": "file_ready",
                            "sub_message_id": sub_id,
                            "file_id": result["file_id"],
                            "file_info": result["file_info"],
                        })
                        del pending[sub_id]
                    continue

                if time.monotonic() < item["deadline"]:
                    continue

                await _mark_pending_failed(
                    chat_id,
                    sub_id,
                    path,
                    item.get("fail_reason") or PENDING_FAIL_REASON_TIMEOUT,
                )
                del pending[sub_id]

            await asyncio.sleep(3)

        # 4. 所有 pending 终态 → 通知订阅连接正常关闭
        await _broadcast_chat_event(chat_id, {"type": "__done__"})

    finally:
        if backend is not None and hasattr(backend, 'aclose'):
            try:
                await backend.aclose()
            except Exception:
                pass


router = APIRouter()



@router.post(
    "/tasks/status",
    response_model=TaskStatusResponse,
    summary="批量查询后台任务是否在运行",
    tags=["Tasks"]
)
async def check_tasks_status(request: TaskStatusRequest):
    """
    用于前端断线重连时对齐后台异步任务的状态。
    """
    running = []
    for tid in request.task_ids:
        if await stream_manager.is_task_running(tid):
            running.append(tid)
    return TaskStatusResponse(running_tasks=running)






async def _start_generation_task(
        background_tasks: BackgroundTasks,
        chat_id: str,
        assistant_message_id: str,
        is_retry: bool = False,
        db: Optional[AsyncSession] = None,
        new_user_turn: bool = False,
):
    # 群成员子会话：统一交给群调度器排队，不直接后台生成。
    # 消息（用户消息 / assistant 占位）已由此前的入口创建，桥接按既有 assistantMessageId 执行。
    if db is not None:
        group_id = await group_service.resolve_group_id_for_member(db, chat_id)
        if group_id:
            await stream_manager.release_generation_lock(chat_id)
            await generation_bridge.enqueue_member_turn(
                db,
                group_id=group_id,
                member_chat_id=chat_id,
                kind=GroupTaskKind.USER_MESSAGE.value,
                payload={"recover_from_error": True} if is_retry else {},
                assistant_message_id=assistant_message_id,
                # 仅「用户在该子会话新发一条消息」算新一次发起沟通；重试/重生成/编辑重发/恢复沿用当前额度
                new_episode=new_user_turn,
            )
            return

    await stream_manager.mark_task_running(assistant_message_id)
    await stream_manager.set_chat_generating(chat_id)
    await chat_status_service.publish_chat_status(chat_id, {"generating": True, "pendingReview": False})
    if is_retry:
        background_tasks.add_task(generation_service._run_retry_generation_task, chat_id, assistant_message_id)
    else:
        background_tasks.add_task(generation_service._run_managed_generation_task, chat_id, assistant_message_id)


async def _touch_chat_task(chat_id: str):
    async with AsyncSessionLocal() as db:
        await chat_crud.touch_chat(db, chat_id)


async def _hydrate_and_validate_messages(
        db_messages: List[chat_model.Message],
        db: AsyncSession
) -> List[schemas.Message]:
    if not db_messages:
        return []

    file_ids_to_hydrate = {
        sub.content for msg in db_messages for sub in msg.sub_messages if sub.type == 'File' and sub.content
    }

    file_info_map = {}
    file_service = FileService(db)
    if file_ids_to_hydrate:
        file_records = await file_service.batch_get_files(list(file_ids_to_hydrate))
        for record in file_records:
            file_info_map[record.id] = file_service.convert_to_schema(record)

    message_responses = []
    for db_message in db_messages:
        message_res = schemas.Message.model_validate(db_message)
        message_res.status = await generation_service._calculate_message_status(db_message)

        for sub_message_res in message_res.sub_messages:
            if sub_message_res.type == 'File' and sub_message_res.content in file_info_map:
                sub_message_res.file_info = file_info_map[sub_message_res.content]
            elif sub_message_res.type == 'McpTool' and sub_message_res.content:
                # 为多模态 tool 结果填充 media 下载 url，供前端展示媒体
                sub_message_res.content = await file_service.hydrate_media_content(sub_message_res.content)

        message_responses.append(message_res)

    return message_responses


@router.get(
    "/chats/{chat_id}/messages",
    response_model=schemas.ChatWithMessages,
    summary="获取单个会话及其消息",
    response_model_exclude_none=True
)
async def read_chat_with_messages(
        chat_id: str,
        background_tasks: BackgroundTasks,
        mark_read: bool = Query(False, description="是否推进会话已读水位（仅用户主动打开会话时为 True）"),
        db: AsyncSession = Depends(get_db)
):
    if mark_read:
        background_tasks.add_task(_touch_chat_task, chat_id)

    db_chat = await chat_crud.get_chat_meta(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get messages for a folder.")

    default_model_setting = await setting_crud.get_setting(db, key="default_model_id")
    default_model_id = default_model_setting.value if default_model_setting else None
    _apply_default_model_to_chat_object(db_chat, default_model_id)

    chat_data = schemas.Chat.model_validate(db_chat)
    chat_response = schemas.ChatWithMessages(**chat_data.model_dump())

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id, latest_usage_only=True)
    chat_response.messages = await _hydrate_and_validate_messages(active_messages, db)

    return chat_response


@router.get(
    "/chats/{chat_id}/usage",
    response_model=schemas.ChatUsageStats,
    summary="统计会话的 token 用量",
    response_model_exclude_none=True
)
async def get_chat_usage_stats(chat_id: str, db: AsyncSession = Depends(get_db)):
    db_chat = await chat_crud.get_chat_meta(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Cannot get usage stats for a folder.")

    return await message_crud.get_chat_usage_stats(db, chat_id=chat_id)


@router.put(
    "/messages/{message_id}",
    response_model=schemas.UpdateMessageResponse,
    summary="更新消息内容并可选择重新生成",
    response_model_exclude_none=True
)
async def update_message_and_regenerate(
        message_id: str,
        message_update: schemas.MessageUpdate,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    new_message_create = schemas.MessageCreate(
        role=db_message.role,
        sub_messages=message_update.sub_messages,
        parentId=db_message.parentId
    )
    new_user_message = await message_crud.create_message(db, message=new_message_create, chat_id=db_message.chatId)

    # Mambo Agent 会话：把用户文件副本写入 /.mambo/chat_user_file/ 并固化标志位
    from backend.services.generation.agent.user_file_copy_service import process_user_message_files
    await process_user_message_files(db, db_message.chatId, new_user_message.id)

    if not message_update.resend:
        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId, latest_usage_only=True)
        populated_user_msg = next((m for m in active_msgs if m.id == new_user_message.id), new_user_message)

        hydrated_user_message = (await _hydrate_and_validate_messages([populated_user_msg], db))[0]
        return schemas.UpdateMessageResponse(
            user_message=hydrated_user_message,
            assistant_message=None
        )

    if db_message.role != schemas.MessageRole.USER:
        raise HTTPException(status_code=400, detail="Resend is only applicable to user messages.")

    assistant_placeholder = await generation_service.prepare_for_regeneration(
        db=db, chat_id=db_message.chatId, base_message_id=new_user_message.id
    )
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id, db=db)

    # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId, latest_usage_only=True)
    populated_user_msg = next((m for m in active_msgs if m.id == new_user_message.id), new_user_message)
    populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

    hydrated_messages = await _hydrate_and_validate_messages([populated_user_msg, populated_assistant_msg], db)

    return schemas.UpdateMessageResponse(
        user_message=hydrated_messages[0],
        assistant_message=hydrated_messages[1]
    )


@router.put(
    "/chats/{chat_id}/messages/{message_id}/activate",
    response_model=List[schemas.Message],
    summary="激活指定的消息分支路径",
    response_model_exclude_none=True
)
async def activate_message_branch(chat_id: str, message_id: str, db: AsyncSession = Depends(get_db)):
    success = await message_crud.activate_message_path(db, message_id=message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id, latest_usage_only=True)
    return await _hydrate_and_validate_messages(active_messages, db)


@router.get(
    "/messages/{message_id}/task-substeps",
    response_model=List[schemas.SubMessage],
    summary="获取消息下的 TaskSubStep 子代理追踪步骤",
    response_model_exclude_none=True
)
async def get_message_task_substeps(
        message_id: str,
        task_group_id: Optional[str] = Query(None, description="可选：按 task_group_id 过滤"),
        db: AsyncSession = Depends(get_db),
):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    subs = await message_crud.get_task_substeps(db, message_id, task_group_id)
    return [schemas.SubMessage.model_validate(s) for s in subs]


@router.delete(
    "/messages/{message_id}",
    response_model=schemas.Message,
    summary="删除单条消息",
    response_model_exclude_none=True
)
async def delete_single_message(message_id: str, db: AsyncSession = Depends(get_db)):
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 修复: 在物理删除前提前完成 Hydrate，防止删除后触发懒加载导致崩溃
    hydrated_messages = await _hydrate_and_validate_messages([db_message], db)

    await message_crud.delete_message(db, message_id=message_id)

    return hydrated_messages[0]


@router.put("/sub-messages/{sub_message_id}", response_model=schemas.SubMessage, summary="更新单个消息分区")
async def update_sub_message(
        sub_message_id: str,
        sub_message_update: schemas.SubMessageUpdate,
        db: AsyncSession = Depends(get_db)
):
    updated_sub_message = await message_crud.update_sub_message(db, sub_message_id, sub_message_update)
    if not updated_sub_message:
        raise HTTPException(status_code=404, detail="SubMessage not found")
    return updated_sub_message


@router.post(
    "/image-runs/{sub_message_id}/rerun",
    summary="对图片子消息重新生成（调参重跑，不写入对话上下文）",
)
async def rerun_image_run(sub_message_id: str, request: ImageRunRerunRequest):
    from backend.services.image_run_service import (
        ImageRunConflictError,
        ImageRunError,
        rerun_image_run as _rerun_image_run,
    )

    allowed_modes = {"Normal", "Mini_Avatar", "Gal_Avatar", "Group", "Spark"}
    if request.mode is not None and request.mode not in allowed_modes:
        raise AppHTTPException(
            status_code=400,
            error_code="INVALID_IMAGE_MODE",
            detail=f"不支持的展示模式: {request.mode}",
        )

    try:
        return await _rerun_image_run(
            sub_message_id=sub_message_id,
            overrides=request.model_dump(),
        )
    except ImageRunConflictError as exc:
        raise AppHTTPException(
            status_code=409, error_code="IMAGE_RUN_IN_PROGRESS", detail=str(exc)
        )
    except ImageRunError as exc:
        raise AppHTTPException(
            status_code=400, error_code="IMAGE_RUN_FAILED", detail=str(exc)
        )


@router.post(
    "/pending-files/{sub_message_id}/fetch",
    response_model=PendingFileFetchResponse,
    summary="手动获取（下载并入库）一条等待超时的待生成文件",
)
async def fetch_pending_file(sub_message_id: str):
    """手动触发一次「查任务 → 下载 → 入库 → 展示」。

    只在文件卡片处于失败态时由前端调用；不会把子消息改回等待态，
    任务仍在生成时直接返回 ``running``，由用户稍后再次点击。
    """
    from backend.services.generation.agent.backend_factory import (
        build_backend_from_chat_id,
    )
    from backend.services.generation.agent.image_gen.factory import (
        build_image_gen_standard_from_chat_id,
    )

    if sub_message_id in _fetch_inflight:
        raise AppHTTPException(
            status_code=409,
            error_code="PENDING_FETCH_IN_PROGRESS",
            detail="该文件正在获取中，请稍候",
        )

    async with AsyncSessionLocal() as db:
        sub = await message_crud.get_sub_message(db, sub_message_id)
        if sub is None or sub.type != SubMessageType.FILE.value:
            raise AppHTTPException(
                status_code=404,
                error_code="PENDING_FILE_NOT_FOUND",
                detail="找不到该文件子消息",
            )

        config = _config_to_dict(sub.config)
        path = config.get("pending_file_path")
        if not path:
            raise AppHTTPException(
                status_code=400,
                error_code="PENDING_FILE_NOT_FOUND",
                detail="该子消息不是待生成文件",
            )

        # 幂等：已经就绪直接返回
        if sub.status == MessageStatus.COMPLETED.value and sub.content:
            fs = FileService(db)
            record = await fs.get_file(sub.content)
            file_info = (
                fs.convert_to_schema(record).model_dump(mode="json") if record else None
            )
            return PendingFileFetchResponse(
                status="completed", file_id=sub.content, file_info=file_info
            )

        db_message = await message_crud.get_message(db, message_id=sub.messageId)
        chat_id = db_message.chatId if db_message else None

    if not chat_id:
        raise AppHTTPException(
            status_code=404, error_code="PENDING_FILE_NOT_FOUND", detail="找不到所属会话"
        )

    task_id = config.get("pending_image_task_id")
    task_info = {
        "task_id": task_id,
        "path": path,
        "prefix": config.get("pending_image_prefix"),
        "count": config.get("pending_image_count"),
    }

    _fetch_inflight.add(sub_message_id)
    backend = None
    try:
        async with AsyncSessionLocal() as db:
            backend = await build_backend_from_chat_id(db, chat_id)
        if backend is None:
            await _mark_pending_failed(
                chat_id, sub_message_id, path, PENDING_FAIL_REASON_NO_BACKEND
            )
            return PendingFileFetchResponse(
                status="failed", error="当前会话没有可用的 backend，无法获取文件"
            )

        if task_id:
            async with AsyncSessionLocal() as db:
                standard = await build_image_gen_standard_from_chat_id(db, chat_id)
            if standard is None:
                await _mark_pending_failed(
                    chat_id, sub_message_id, path, PENDING_FAIL_REASON_NO_BACKEND
                )
                return PendingFileFetchResponse(
                    status="failed", error="生图配置不可用，无法获取文件"
                )

            outcome, error = await asyncio.wait_for(
                _drive_task_download(standard, backend, task_info),
                timeout=PENDING_FETCH_TIMEOUT,
            )
            if outcome == "failed":
                await _mark_pending_failed(
                    chat_id, sub_message_id, path, PENDING_FAIL_REASON_TASK_FAILED
                )
                return PendingFileFetchResponse(status="failed", error=error)
            if outcome == "running":
                return PendingFileFetchResponse(
                    status="running",
                    error=error or "文件仍在生成中，请稍后再试",
                )

        result = await asyncio.wait_for(
            _process_pending_file(backend, sub_message_id, path),
            timeout=PENDING_FETCH_TIMEOUT,
        )
        if result["type"] != "file_ready":
            return PendingFileFetchResponse(
                status="running", error="文件尚未写完，请稍后再试"
            )

        await _broadcast_chat_event(chat_id, {
            "type": "file_ready",
            "sub_message_id": sub_message_id,
            "file_id": result["file_id"],
            "file_info": result["file_info"],
        })
        return PendingFileFetchResponse(
            status="completed",
            file_id=result["file_id"],
            file_info=result["file_info"],
        )
    except asyncio.TimeoutError:
        await _mark_pending_failed(
            chat_id, sub_message_id, path, PENDING_FAIL_REASON_DOWNLOAD_FAILED
        )
        return PendingFileFetchResponse(
            status="failed", error="获取文件超时，请稍后重试"
        )
    except Exception as exc:  # noqa: BLE001 - 统一转成失败态，不抛 500
        logger.warning("手动获取文件失败(sub=%s): %s", sub_message_id, exc, exc_info=True)
        await _mark_pending_failed(
            chat_id, sub_message_id, path, PENDING_FAIL_REASON_DOWNLOAD_FAILED
        )
        return PendingFileFetchResponse(status="failed", error=str(exc) or "获取文件失败")
    finally:
        _fetch_inflight.discard(sub_message_id)
        if backend is not None and hasattr(backend, "aclose"):
            try:
                await backend.aclose()
            except Exception:
                pass


@router.post("/messages/{message_id}/stop", status_code=status.HTTP_202_ACCEPTED, summary="请求停止AI生成")
async def stop_generation(message_id: str, db: AsyncSession = Depends(get_db)):
    await stream_manager.request_cancellation(message_id)
    await stream_manager.mark_task_completed(message_id)

    # 立即释放该会话的生成锁，使前端停止后可以立刻重新生成。
    db_message = await message_crud.get_message(db, message_id=message_id)
    if db_message:
        await stream_manager.release_generation_lock(db_message.chatId)

    return {"message": "Cancellation requested."}


@router.post(
    "/messages/{message_id}/compress-history",
    status_code=status.HTTP_202_ACCEPTED,
    summary="压缩指定消息及之前的所有对话历史"
)
async def compress_history_above_message(
        message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    if not await maintenance.wait_vacuum_finished(timeout=60):
        raise AppHTTPException(status_code=503, error_code="DB_MAINTENANCE", detail="数据库维护中（VACUUM），请稍后重试。")
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    if db_message.role != schemas.MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="History compression can only be initiated from an assistant's message."
        )

    background_tasks.add_task(
        generation_service.run_zip_history_generation_task,
        chat_id=db_message.chatId,
        target_message_id=message_id
    )
    return {"message": "History compression task has been initiated."}


@router.post(
    "/chats/{chat_id}/prepare-generate",
    response_model=schemas.PrepareGenerateResponse,
    summary="准备并开始生成AI回复",
    response_model_exclude_none=True
)
async def prepare_to_generate(
        chat_id: str,
        request: schemas.GenerateRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    if not await maintenance.wait_vacuum_finished(timeout=60):
        raise AppHTTPException(status_code=503, error_code="DB_MAINTENANCE", detail="数据库维护中（VACUUM），请稍后重试。")
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise AppHTTPException(status_code=409, error_code="GENERATION_IN_PROGRESS", detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        user_message, assistant_placeholder = await generation_service.create_user_message_and_prepare_generation(
            db=db, chat_id=chat_id, request=request
        )
        await _start_generation_task(
            background_tasks, chat_id, assistant_placeholder.id, db=db, new_user_turn=True
        )

        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        populated_user_msg = next((m for m in active_msgs if m.id == user_message.id), user_message)
        populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

        hydrated_messages = await _hydrate_and_validate_messages([populated_user_msg, populated_assistant_msg], db)

        return schemas.PrepareGenerateResponse(
            user_message=hydrated_messages[0],
            assistant_message=hydrated_messages[1]
        )
    except Exception:
        await stream_manager.release_generation_lock(chat_id)
        raise


@router.post(
    "/chats/{chat_id}/prepare-regenerate/{from_message_id}",
    response_model=schemas.Message,
    summary="准备并开始重新生成AI回复",
    response_model_exclude_none=True
)
async def prepare_to_regenerate(
        chat_id: str,
        from_message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
):
    if not await maintenance.wait_vacuum_finished(timeout=60):
        raise AppHTTPException(status_code=503, error_code="DB_MAINTENANCE", detail="数据库维护中（VACUUM），请稍后重试。")
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise AppHTTPException(status_code=409, error_code="GENERATION_IN_PROGRESS", detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        assistant_placeholder = await generation_service.prepare_for_regeneration(
            db=db, chat_id=chat_id, base_message_id=from_message_id,
        )

        await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id, db=db)

        # 修复: 从活跃路径中重新获取，以避免 DetachedInstanceError 并装配 sibling 元数据
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
        populated_assistant_msg = next((m for m in active_msgs if m.id == assistant_placeholder.id), assistant_placeholder)

        hydrated_messages = await _hydrate_and_validate_messages([populated_assistant_msg], db)
        return hydrated_messages[0]
    except Exception:
        await stream_manager.release_generation_lock(chat_id)
        raise


@router.post(
    "/messages/{message_id}/retry",
    response_model=schemas.Message,
    summary="重试失败的生成任务（从 LangGraph checkpoint 恢复）",
    response_model_exclude_none=True
)
async def retry_failed_generation(
        message_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    if not await maintenance.wait_vacuum_finished(timeout=60):
        raise AppHTTPException(status_code=503, error_code="DB_MAINTENANCE", detail="数据库维护中（VACUUM），请稍后重试。")
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    if db_message.role != schemas.MessageRole.ASSISTANT:
        raise HTTPException(status_code=400, detail="Retry is only applicable to assistant messages.")

    calculated_status = await generation_service._calculate_message_status(db_message)
    if calculated_status != schemas.MessageStatus.FAILED:
        raise HTTPException(status_code=400, detail="Retry is only applicable to failed messages.")

    if not await stream_manager.try_acquire_generation_lock(db_message.chatId):
        raise AppHTTPException(status_code=409, error_code="GENERATION_IN_PROGRESS", detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        await _start_generation_task(background_tasks, db_message.chatId, message_id, is_retry=True, db=db)

        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
        populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

        hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
        response_message = hydrated_messages[0]
        response_message.status = schemas.MessageStatus.GENERATING

        return response_message
    except Exception:
        await stream_manager.release_generation_lock(db_message.chatId)
        raise


@router.post(
    "/chats/{chat_id}/generate-title",
    status_code=status.HTTP_202_ACCEPTED,
    summary="自动生成会话标题"
)
async def generate_chat_title(
        chat_id: str,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    db_chat = await chat_crud.get_chat(db, chat_id=chat_id)
    if not db_chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if db_chat.itemType != 'chat':
        raise HTTPException(status_code=400, detail="Title generation is only applicable to chats, not folders.")

    background_tasks.add_task(generation_service.run_title_generation_task, chat_id)
    return {"message": "Title generation has been initiated."}


@router.get(
    "/chats/{chat_id}/stream-response/{assistant_message_id}",
    summary="订阅AI回复的流式输出",
    response_description="一个Server-Sent Events (SSE)流。"
)
async def stream_response(
        chat_id: str,
        assistant_message_id: str,
        db: AsyncSession = Depends(get_db)
):
    return StreamingResponse(
        generation_service.subscribe_to_stream(db, assistant_message_id),
        media_type="text/event-stream"
    )

@router.post(
    "/messages/{message_id}/review-tool",
    response_model=schemas.Message,
    summary="提交工具调用审核决策",
    response_model_exclude_none=True
)
async def review_tool_call(
        message_id: str,
        request: ToolApprovalRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    from backend.schemas.message import ReviewToolContent, McpToolContent

    db_sub = await message_crud.get_sub_message(db, request.sub_message_id)
    if not db_sub or db_sub.messageId != message_id or db_sub.type != SubMessageType.REVIEW_TOOL.value:
        raise HTTPException(status_code=404, detail="Review tool request not found.")

    review_content = ReviewToolContent.from_json_string(db_sub.content)
    review_content.decision = request.decision

    # 编辑决策时，同步更新 arguments 到 REVIEW_TOOL 和 MCP_TOOL 子消息
    if request.decision.type == 'edit' and request.decision.edited_action:
        review_content.arguments = request.decision.edited_action.args

        db_message = await message_crud.get_message(db, message_id=message_id)
        for sub in db_message.sub_messages:
            if sub.type == SubMessageType.MCP_TOOL.value:
                try:
                    mcp = McpToolContent.from_json_string(sub.content)
                    if getattr(mcp, 'tool_call_id', None) == review_content.tool_call_id:
                        mcp.arguments = request.decision.edited_action.args
                        await message_crud.update_sub_message(
                            db, sub.id,
                            schemas.SubMessageUpdate(content=mcp.to_json_string())
                        )
                except Exception:
                    pass

    await message_crud.update_sub_message(
        db,
        request.sub_message_id,
        schemas.SubMessageUpdate(content=review_content.to_json_string())
    )

    db_message = await message_crud.get_message(db, message_id=message_id)
    pending_review_subs = [
        sub for sub in db_message.sub_messages
        if sub.type == SubMessageType.REVIEW_TOOL.value and sub.status == MessageStatus.PENDING_REVIEW.value
    ]

    all_decided = True
    for sub in pending_review_subs:
        content = ReviewToolContent.from_json_string(sub.content)
        if content.decision is None:
            all_decided = False
            break

    is_resuming = False

    if all_decided and pending_review_subs:
        sub_ids = [sub.id for sub in pending_review_subs]
        affected_rows = await message_crud.batch_update_sub_messages_status_optimistic(
            db, sub_ids, MessageStatus.PENDING_REVIEW, MessageStatus.COMPLETED
        )

        if affected_rows == len(sub_ids):
            await _start_generation_task(background_tasks, db_message.chatId, message_id, db=db)
            is_resuming = True

    # 修复: 从活跃路径中重新获取，以装配 sibling 元数据
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING
    else:
        await chat_status_service.publish_current_status(db_message.chatId)

    return response_message


@router.post(
    "/messages/{message_id}/answer-ask-user",
    response_model=schemas.Message,
    summary="提交 ask_user 问题回答",
    response_model_exclude_none=True
)
async def answer_ask_user(
        message_id: str,
        request: AskUserAnswerRequest,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
):
    from backend.schemas.message import AskUserContent

    db_sub = await message_crud.get_sub_message(db, request.sub_message_id)
    if not db_sub or db_sub.messageId != message_id or db_sub.type != SubMessageType.ASK_USER.value:
        raise HTTPException(status_code=404, detail="AskUser request not found.")

    ask_content = AskUserContent.from_json_string(db_sub.content)
    ask_content.answers = request.answers
    ask_content.ask_status = request.ask_status

    await message_crud.update_sub_message(
        db,
        request.sub_message_id,
        schemas.SubMessageUpdate(content=ask_content.to_json_string())
    )

    db_message = await message_crud.get_message(db, message_id=message_id)
    pending_ask_subs = [
        sub for sub in db_message.sub_messages
        if sub.type == SubMessageType.ASK_USER.value and sub.status == MessageStatus.PENDING_REVIEW.value
    ]

    all_answered = True
    for sub in pending_ask_subs:
        try:
            content = AskUserContent.from_json_string(sub.content)
            if content.answers is None:
                all_answered = False
                break
        except (ValueError, ImportError):
            all_answered = False
            break

    is_resuming = False

    if all_answered and pending_ask_subs:
        sub_ids = [sub.id for sub in pending_ask_subs]
        affected_rows = await message_crud.batch_update_sub_messages_status_optimistic(
            db, sub_ids, MessageStatus.PENDING_REVIEW, MessageStatus.COMPLETED
        )

        if affected_rows == len(sub_ids):
            await _start_generation_task(background_tasks, db_message.chatId, message_id, db=db)
            is_resuming = True

    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING
    else:
        await chat_status_service.publish_current_status(db_message.chatId)

    return response_message


@router.get(
    "/chats/{chat_id}/wait-for-files",
    summary="等待会话中待生成文件就绪（SSE，按会话聚合）",
)
async def wait_for_pending_files(chat_id: str, db: AsyncSession = Depends(get_db)):
    """前端进入会话时建立一条聚合 SSE 连接，等待该会话所有 pending 文件。

    连接建立时先推送已终态（completed/failed）文件的事件；仍有 waiting 文件
    则启动/复用本会话的轮询任务（共享 backend），全部终态后服务端正常关闭连接。
    """
    db_chat = await chat_crud.get_chat_meta(db, chat_id=chat_id)
    if db_chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    msgs = await message_crud.get_messages_by_chat(db, chat_id=chat_id)

    # 1. 状态对齐扫描：已终态立即推送，waiting 纳入轮询
    file_ids_to_hydrate = {
        sub.content for m in msgs for sub in m.sub_messages
        if sub.type == SubMessageType.FILE.value and sub.status == MessageStatus.COMPLETED.value and sub.content
    }
    file_info_map = {}
    if file_ids_to_hydrate:
        fs = FileService(db)
        file_records = await fs.batch_get_files(list(file_ids_to_hydrate))
        for record in file_records:
            file_info_map[record.id] = fs.convert_to_schema(record).model_dump(mode='json')

    initial_events: list[dict] = []
    has_pending = False
    for m in msgs:
        for sub in m.sub_messages:
            if sub.type != SubMessageType.FILE.value:
                continue
            if sub.status == MessageStatus.COMPLETED.value and sub.content:
                initial_events.append({
                    "type": "file_ready",
                    "sub_message_id": sub.id,
                    "file_id": sub.content,
                    "file_info": file_info_map.get(sub.content),
                })
            elif sub.status == MessageStatus.FAILED.value:
                raw_cfg = sub.config
                if isinstance(raw_cfg, str):
                    try:
                        raw_cfg = json.loads(raw_cfg)
                    except json.JSONDecodeError:
                        raw_cfg = {}
                path = raw_cfg.get("pending_file_path") if isinstance(raw_cfg, dict) else None
                initial_events.append({
                    "type": "file_timeout",
                    "sub_message_id": sub.id,
                    "path": path or "",
                })
            elif sub.status == MessageStatus.WAITING.value:
                raw_cfg = sub.config
                if isinstance(raw_cfg, str):
                    try:
                        raw_cfg = json.loads(raw_cfg)
                    except json.JSONDecodeError:
                        raw_cfg = {}
                path = raw_cfg.get("pending_file_path") if isinstance(raw_cfg, dict) else None
                if path:
                    has_pending = True

    # 2. 订阅队列 + 启动/复用轮询任务
    queue: asyncio.Queue = asyncio.Queue()
    _chat_subscribers.setdefault(chat_id, set()).add(queue)
    for event in initial_events:
        queue.put_nowait(event)

    if has_pending:
        task = _chat_pending_tasks.get(chat_id)
        if task is None:
            task = asyncio.create_task(_poll_chat_pending_files(chat_id))
            _chat_pending_tasks[chat_id] = task
            task.add_done_callback(lambda _: _chat_pending_tasks.pop(chat_id, None))
    else:
        queue.put_nowait({"type": "__done__"})

    async def event_stream():
        try:
            while True:
                event = await queue.get()
                if isinstance(event, dict) and event.get("type") == "__done__":
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            _chat_subscribers.get(chat_id, set()).discard(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")