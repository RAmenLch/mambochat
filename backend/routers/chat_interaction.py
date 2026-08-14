# backend/routers/chat_interaction.py

import asyncio
import json
import time
from pathlib import PurePosixPath

from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from typing import List, Optional

from backend.services import generation_service
from backend.services.stream_manager_service import stream_manager
from backend.services.file_service import FileService
from backend.services import maintenance
from backend.crud import chat_crud, message_crud, setting_crud
from backend import schemas
from backend.models import chat_model
from backend.database import get_db, AsyncSessionLocal
from backend.routers.chat_management import _apply_default_model_to_chat_object
from backend.schemas import SubMessageType, MessageStatus
from backend.schemas.message import ToolApprovalRequest, SubMessageConfig, SubMessageUpdate
from backend.schemas.enums import FileManagementType

from mambo_agents.backends.schemas import VirtualPath
from mambo_agents.backends.protocol import _get_mime_type

from pydantic import BaseModel

class TaskStatusRequest(BaseModel):
    task_ids: List[str]

class TaskStatusResponse(BaseModel):
    running_tasks: List[str]


class AskUserAnswerRequest(BaseModel):
    sub_message_id: str
    answers: List[str]
    ask_status: str = "answered"


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


async def _process_pending_file(
    backend,
    sub_message_id: str,
    path: str,
) -> dict:
    """下载 → 稳定性校验 → 入库 → 更新子消息。

    返回 {"type": "file_ready", "file_id", "file_info"} 或
         {"type": "still_writing"}（文件未写完，等待下一轮）。
    """
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
    mime = _get_mime_type(path)

    if content:
        sample = content[:8192]
        try:
            sample.decode("utf-8")
            from backend.utils.file_utils import FileUtils
            mime = FileUtils.correct_mime_type(filename, mime, sample)
        except (UnicodeDecodeError, ValueError, LookupError):
            pass

    async with AsyncSessionLocal() as db:
        fs = FileService(db)
        db_file = await fs.save_file_from_bytes(
            data=content or b"",
            filename=filename,
            mime_type=mime,
            management_type=[FileManagementType.SUB_MESSAGE.value],
            sub_path="chat_attachments",
        )

        # 保留创建时设置的 show_tool_mode（防止轮询完成时被覆盖）
        existing_sub = await message_crud.get_sub_message(db, sub_message_id)
        show_tool_mode = None
        if existing_sub and existing_sub.config:
            raw_cfg = existing_sub.config
            if isinstance(raw_cfg, str):
                raw_cfg = json.loads(raw_cfg)
            show_tool_mode = raw_cfg.get("show_tool_mode") if isinstance(raw_cfg, dict) else getattr(raw_cfg, "show_tool_mode", None)

        await message_crud.update_sub_message(
            db,
            sub_message_id,
            SubMessageUpdate(
                content=db_file.id,
                status=MessageStatus.COMPLETED,
                config=SubMessageConfig(
                    context_participation_length=0,
                    pending_file_path=None,
                    pending_file_timeout=None,
                    show_tool_mode=show_tool_mode,
                ),
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
) -> dict[str, tuple[str, int]]:
    """扫描会话下所有等待中的文件子消息，返回 {sub_message_id: (path, timeout)}。"""
    pending: dict[str, tuple[str, int]] = {}
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
            timeout = raw_cfg.get("pending_file_timeout") or 300
            pending[sub.id] = (path, int(timeout))
    return pending


async def _poll_chat_pending_files(chat_id: str) -> None:
    """轮询会话下所有待生成文件，就绪/超时后入库并广播事件。"""
    from backend.services.generation.agent.backend_factory import (
        build_backend_from_chat_id,
    )

    backend = None
    try:
        async with AsyncSessionLocal() as db:
            backend = await build_backend_from_chat_id(db, chat_id)

        # sub_message_id -> (path, timeout, deadline)
        pending: dict[str, tuple[str, int, float]] = {}

        while True:
            # 1. 与 DB 同步 pending 集合（新文件自动纳入，已终态移除）
            async with AsyncSessionLocal() as db:
                db_pending = await _scan_chat_pending_sub_messages(db, chat_id)

            now = time.monotonic()
            for sub_id in list(pending.keys()):
                if sub_id not in db_pending:
                    del pending[sub_id]
            for sub_id, (path, timeout) in db_pending.items():
                if sub_id not in pending:
                    pending[sub_id] = (path, timeout, now + timeout)

            if not pending:
                break

            # 2. 逐个处理：超时 → failed；就绪 → 入库 + completed
            for sub_id, (path, timeout, deadline) in list(pending.items()):
                if time.monotonic() >= deadline:
                    async with AsyncSessionLocal() as db:
                        await message_crud.update_sub_message(
                            db,
                            sub_id,
                            SubMessageUpdate(status=MessageStatus.FAILED),
                        )
                    await _broadcast_chat_event(chat_id, {
                        "type": "file_timeout",
                        "sub_message_id": sub_id,
                        "path": path,
                    })
                    del pending[sub_id]
                    continue

                try:
                    pp = PurePosixPath(path)
                    glob_result = await backend.aglob(pp.name, VirtualPath(str(pp.parent)))
                    file_appeared = glob_result.error is None and bool(glob_result.matches)
                except Exception:
                    file_appeared = False

                if not file_appeared:
                    continue

                result = await _process_pending_file(backend, sub_id, path)
                if result["type"] == "file_ready":
                    await _broadcast_chat_event(chat_id, {
                        "type": "file_ready",
                        "sub_message_id": sub_id,
                        "file_id": result["file_id"],
                        "file_info": result["file_info"],
                    })
                    del pending[sub_id]

            await asyncio.sleep(3)

        # 3. 所有 pending 终态 → 通知订阅连接正常关闭
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
        is_retry: bool = False
):
    await stream_manager.mark_task_running(assistant_message_id)
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
    if file_ids_to_hydrate:
        file_service = FileService(db)
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

        message_responses.append(message_res)

    return message_responses


@router.get(
    "/chats/{chat_id}/messages",
    response_model=schemas.ChatWithMessages,
    summary="获取单个会话及其消息",
    response_model_exclude_none=True
)
async def read_chat_with_messages(chat_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
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
    await _start_generation_task(background_tasks, db_message.chatId, assistant_placeholder.id)

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
        raise HTTPException(status_code=503, detail="数据库维护中（VACUUM），请稍后重试。")
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
        raise HTTPException(status_code=503, detail="数据库维护中（VACUUM），请稍后重试。")
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        user_message, assistant_placeholder = await generation_service.create_user_message_and_prepare_generation(
            db=db, chat_id=chat_id, request=request
        )
        await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

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
        raise HTTPException(status_code=503, detail="数据库维护中（VACUUM），请稍后重试。")
    if not await stream_manager.try_acquire_generation_lock(chat_id):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        assistant_placeholder = await generation_service.prepare_for_regeneration(
            db=db, chat_id=chat_id, base_message_id=from_message_id,
        )

        await _start_generation_task(background_tasks, chat_id, assistant_placeholder.id)

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
        raise HTTPException(status_code=503, detail="数据库维护中（VACUUM），请稍后重试。")
    db_message = await message_crud.get_message(db, message_id=message_id)
    if not db_message:
        raise HTTPException(status_code=404, detail="Message not found")

    if db_message.role != schemas.MessageRole.ASSISTANT:
        raise HTTPException(status_code=400, detail="Retry is only applicable to assistant messages.")

    calculated_status = await generation_service._calculate_message_status(db_message)
    if calculated_status != schemas.MessageStatus.FAILED:
        raise HTTPException(status_code=400, detail="Retry is only applicable to failed messages.")

    if not await stream_manager.try_acquire_generation_lock(db_message.chatId):
        raise HTTPException(status_code=409, detail="该会话已有正在进行的生成任务，请等待完成后再试。")

    try:
        await _start_generation_task(background_tasks, db_message.chatId, message_id, is_retry=True)

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
            await _start_generation_task(background_tasks, db_message.chatId, message_id)
            is_resuming = True

    # 修复: 从活跃路径中重新获取，以装配 sibling 元数据
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING

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
            await _start_generation_task(background_tasks, db_message.chatId, message_id)
            is_resuming = True

    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
    populated_msg = next((m for m in active_msgs if m.id == message_id), db_message)

    hydrated_messages = await _hydrate_and_validate_messages([populated_msg], db)
    response_message = hydrated_messages[0]

    if is_resuming:
        response_message.status = schemas.MessageStatus.GENERATING

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