# backend/routers/kb_management.py
import asyncio
import json

from fastapi import APIRouter, Depends, UploadFile, File, status, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend import schemas
from backend.schemas import kb as kb_schemas
from backend.services.kb_service import KnowledgeBaseService
from backend.crud import kb_crud
from backend.services.stream_manager_service import stream_manager

router = APIRouter()


@router.post(
    "/",
    response_model=schemas.Resource,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库"
)
async def create_knowledge_base(
        kb_data: kb_schemas.KBCreate,
        db: AsyncSession = Depends(get_db)
):
    """
    创建一个新的知识库资源。
    需要指定 Embedding 模型 ID，系统会校验模型类型及维度支持情况。
    """
    service = KnowledgeBaseService(db)
    try:
        return await service.create_knowledge_base(kb_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{kb_id}/upload",
    response_model=schemas.Resource,
    status_code=status.HTTP_201_CREATED,
    summary="上传文件至知识库"
)
async def upload_file_to_kb(
        kb_id: str,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    """
    上传文件到指定的知识库。
    仅执行文件保存和元数据创建，不触发切分和嵌入任务。
    后续需调用 /config 接口保存配置，再调用 /task 接口启动处理。
    """
    service = KnowledgeBaseService(db)
    return await service.upload_file(kb_id=kb_id, file=file)


@router.put(
    "/files/{resource_id}/config",
    response_model=schemas.Resource,
    status_code=status.HTTP_200_OK,
    summary="更新文件切分配置"
)
async def update_kb_file_config(
        resource_id: str,
        config_request: kb_schemas.KBUpdateConfigRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    更新知识库文件的切分配置（Splitter Config）。
    此操作会更新 ResourceVersion 的 attributes。
    """
    service = KnowledgeBaseService(db)
    return await service.update_kb_file_config(resource_id, config_request)


@router.post(
    "/files/{resource_id}/task",
    status_code=status.HTTP_200_OK,
    summary="管理文件处理任务"
)
async def run_kb_file_task(
        resource_id: str,
        request: kb_schemas.KBRunTaskRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    启动、恢复或停止文件的切分与嵌入任务。
    - Start: 使用当前保存的配置覆盖更新，重新切分。
    - Resume: 断点续连，仅处理未完成的切片。需确保当前配置与上次运行配置一致，否则报错。
    - Stop: 停止当前正在运行的任务。
    """
    service = KnowledgeBaseService(db)
    return await service.handle_task_action(resource_id, request)


@router.delete(
    "/files/{resource_id}",
    response_model=schemas.Resource,
    status_code=status.HTTP_200_OK,
    summary="删除知识库文件"
)
async def delete_kb_file(
        resource_id: str,
        db: AsyncSession = Depends(get_db)
):
    """
    删除知识库文件。
    会清理关联的向量数据和切片记录，然后删除资源。
    """
    service = KnowledgeBaseService(db)
    return await service.delete_kb_file(resource_id)


@router.post(
    "/search",
    response_model=kb_schemas.KBSearchResponse,
    summary="向量检索"
)
async def search_knowledge_base(
        request: kb_schemas.KBSearchRequest,
        db: AsyncSession = Depends(get_db)
):
    """
    在知识库中进行语义搜索。
    如果指定了 kb_id，则使用该知识库配置的模型进行 Embedding 和检索。
    """
    service = KnowledgeBaseService(db)
    return await service.search_kb(request)


async def _kb_task_stream_generator(resource_id: str):
    """
    KB 任务进度的 SSE 生成器。
    逻辑：
    1. 获取当前综合状态快照并立即推送。
    2. 如果状态为活跃状态（CLEANING, READING, SPLITTING, EMBEDDING），则订阅消息队列持续推送进度。
    3. 否则，发送结束信号并关闭连接。
    """
    # 1. 获取并推送初始状态
    async with AsyncSessionLocal() as session:
        service = KnowledgeBaseService(session)
        # get_comprehensive_file_status 内部已处理僵尸任务检测
        initial_status = await service.get_comprehensive_file_status(resource_id)

    # 推送初始状态快照
    yield f"data: {initial_status.model_dump_json()}\n\n"

    # 定义需要进入流式监听的活跃状态
    active_statuses = {
        kb_schemas.KBFileStatus.CLEANING,
        kb_schemas.KBFileStatus.READING,
        kb_schemas.KBFileStatus.SPLITTING,
        kb_schemas.KBFileStatus.EMBEDDING
    }

    # 2. 根据状态决定是否进入流式监听
    if initial_status.file_status in active_statuses:
        queue = await stream_manager.subscribe(resource_id)
        try:
            while True:
                data = await queue.get()

                if data is None:
                    # 任务完成或停止，发送结束信号
                    yield f"event: end\ndata: Task finished\n\n"
                    break

                # data 已经是 KBProcessingStatus 的字典形式 (由 Service 层生成)
                # 直接序列化为 JSON 字符串推送给前端
                yield f"data: {json.dumps(data, default=str)}\n\n"

                queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            await stream_manager.unsubscribe(resource_id, queue)
    else:
        # 非进行中状态，直接结束
        yield f"event: end\ndata: Task finished\n\n"


@router.get(
    "/files/{resource_id}/progress",
    summary="订阅文件处理进度 (SSE)"
)
async def subscribe_kb_file_progress(resource_id: str):
    """
    订阅指定文件的切分/嵌入任务进度。
    返回 Server-Sent Events (SSE) 流。
    连接建立时会立即返回一次当前状态快照。
    """
    return StreamingResponse(
        _kb_task_stream_generator(resource_id),
        media_type="text/event-stream"
    )
