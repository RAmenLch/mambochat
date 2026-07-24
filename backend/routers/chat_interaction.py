# backend/routers/chat_interaction.py

import asyncio
import json
import time
from pathlib import PurePosixPath

from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from typing import List, Optional

from backend.services import generation_service
from backend.services.stream_manager_service import stream_manager
from backend.services.file_service import FileService
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


_pending_file_tasks: dict[str, asyncio.Task] = {}


async def _poll_and_persist_file(
    sub_message_id: str,
    path: str,
    timeout: int,
    chat_id: str,
) -> dict:
    """轮询等待文件生成，成功后入库并更新子消息。

    返回 {"type": "file_ready", "file_id": "...", "file_info": {...}} 或
         {"type": "file_timeout", "path": "..."}
    """
    from backend.services.generation.agent.backend_factory import (
        build_backend_from_chat_id,
    )

    print(f"[PendingFile] Polling started: sub={sub_message_id} path={path} timeout={timeout}s chat={chat_id}")

    backend = None
    poll_count = 0
    try:
        async with AsyncSessionLocal() as db:
            print(f"[PendingFile] Building backend for chat={chat_id}...")
            backend = await build_backend_from_chat_id(db, chat_id)
            print(f"[PendingFile] Backend built: {type(backend).__name__}")

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            poll_count += 1
            remaining = int(deadline - time.monotonic())
            try:
                pp = PurePosixPath(path)
                glob_result = await backend.aglob(pp.name, VirtualPath(str(pp.parent)))
                file_appeared = glob_result.error is None and bool(glob_result.matches)
                print(f"[PendingFile] Poll #{poll_count}: aglob({pp.name}, {str(pp.parent)}) -> error={glob_result.error} matches={glob_result.matches} (appeared={file_appeared}) remaining={remaining}s")
            except Exception as exc:
                print(f"[PendingFile] Poll #{poll_count}: aglob error: {exc}")
                file_appeared = False

            if file_appeared:
                print(f"[PendingFile] File detected, downloading (pass 1)...")
                r1 = await backend.adownload_files([VirtualPath(path)])
                size1 = len(r1[0].content) if r1 and r1[0].content else 0
                print(f"[PendingFile] Download pass 1: size={size1}")

                if size1 == 0:
                    print(f"[PendingFile] Size=0, waiting 3s before next poll...")
                    await asyncio.sleep(3)
                    continue

                await asyncio.sleep(2)
                print(f"[PendingFile] Stability check: downloading pass 2...")
                r2 = await backend.adownload_files([VirtualPath(path)])
                size2 = len(r2[0].content) if r2 and r2[0].content else 0
                print(f"[PendingFile] Download pass 2: size={size2}")

                if size1 != size2:
                    print(f"[PendingFile] Sizes differ ({size1} vs {size2}), file still writing, retrying...")
                    continue

                print(f"[PendingFile] File stable, persisting...")
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
                    print(f"[PendingFile] File saved: id={db_file.id} filename={filename} mime={mime}")

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
                    print(f"[PendingFile] Sub-message updated: {sub_message_id} -> COMPLETED")

                    file_schema = fs.convert_to_schema(db_file)
                    file_info = file_schema.model_dump(mode='json')

                print(f"[PendingFile] SUCCESS: file_ready file_id={db_file.id}")
                return {
                    "type": "file_ready",
                    "file_id": db_file.id,
                    "file_info": file_info,
                }

            await asyncio.sleep(3)

        print(f"[PendingFile] TIMEOUT after {poll_count} polls: path={path} never appeared")
        async with AsyncSessionLocal() as db:
            await message_crud.update_sub_message(
                db,
                sub_message_id,
                SubMessageUpdate(status=MessageStatus.FAILED),
            )
        return {"type": "file_timeout", "path": path}

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

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
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
        active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
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
    active_msgs = await message_crud.get_messages_by_chat(db, chat_id=db_message.chatId)
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

    active_messages = await message_crud.get_messages_by_chat(db, chat_id=chat_id)
    return await _hydrate_and_validate_messages(active_messages, db)


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
    "/sub-messages/{sub_message_id}/wait-for-file",
    summary="等待待生成文件就绪（SSE）",
)
async def wait_for_pending_file(
    sub_message_id: str,
    db: AsyncSession = Depends(get_db),
):
    print(f"[PendingFile SSE] Connection received for sub={sub_message_id}")

    sub = await message_crud.get_sub_message(db, sub_message_id)
    if not sub or sub.type != SubMessageType.FILE.value:
        print(f"[PendingFile SSE] ERROR: sub not found or not FILE type")
        raise HTTPException(404, "Sub-message not found or not a File type")

    raw_config = sub.config
    if isinstance(raw_config, str):
        raw_config = json.loads(raw_config)
    config = SubMessageConfig(**raw_config)

    path = config.pending_file_path
    timeout = config.pending_file_timeout or 300
    print(f"[PendingFile SSE] sub={sub_message_id} status={sub.status} content={sub.content!r} path={path} timeout={timeout}")

    if sub.status == MessageStatus.COMPLETED.value and sub.content:
        print(f"[PendingFile SSE] File already completed, returning immediately: file_id={sub.content}")
        async def immediate():
            yield f"data: " + json.dumps({
                "type": "file_ready",
                "file_id": sub.content,
            }) + "\n\n"
        return StreamingResponse(immediate(), media_type="text/event-stream")

    if not path or sub.status != MessageStatus.WAITING.value:
        print(f"[PendingFile SSE] ERROR: not in pending state (path={path} status={sub.status})")
        raise HTTPException(400, "File is not in pending state")

    db_message = await message_crud.get_message(db, sub.messageId)
    if not db_message:
        raise HTTPException(404, "Message not found")
    chat_id = db_message.chatId

    task = _pending_file_tasks.get(sub_message_id)
    if task is None:
        print(f"[PendingFile SSE] Creating new poll task for sub={sub_message_id} chat={chat_id}")
        task = asyncio.create_task(
            _poll_and_persist_file(sub_message_id, path, timeout, chat_id)
        )
        _pending_file_tasks[sub_message_id] = task
        task.add_done_callback(lambda _: _pending_file_tasks.pop(sub_message_id, None))
    else:
        print(f"[PendingFile SSE] Reusing existing poll task for sub={sub_message_id}")

    async def event_stream():
        try:
            result = await asyncio.shield(task)
            print(f"[PendingFile SSE] Task completed for sub={sub_message_id}: {result['type']}")
            yield f"data: " + json.dumps(result) + "\n\n"
        except asyncio.CancelledError:
            print(f"[PendingFile SSE] Client disconnected for sub={sub_message_id}")
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")