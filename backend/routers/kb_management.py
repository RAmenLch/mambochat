# backend/routers/kb_management.py

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, AsyncSessionLocal
from backend import schemas
from backend.schemas import kb as kb_schemas
from backend.services.kb_service import KnowledgeBaseService
from backend.crud import kb_crud

router = APIRouter()


async def _run_embedding_background(resource_id: str):
    """
    后台任务包装器：为后台 Embedding 任务创建独立的数据库会话。
    """
    async with AsyncSessionLocal() as db:
        service = KnowledgeBaseService(db)
        await service.run_embedding_task(resource_id)


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
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    """
    上传文件到指定的知识库。
    流程：
    1. 校验文件类型（仅支持纯文本）。
    2. 保存物理文件。
    3. 在数据库中创建 File 和 Resource 记录。
    4. 切分文本并批量存入 ResourceKBChunk 表 (状态为 PENDING)。
    5. 触发后台任务进行向量化处理。
    """
    service = KnowledgeBaseService(db)

    # 执行文件入库和切分逻辑
    new_resource = await service.ingest_file(kb_id=kb_id, file=file)

    # 添加后台向量化任务
    # 注意：不能直接使用当前的 db 会话，因为它会在请求结束时关闭
    background_tasks.add_task(_run_embedding_background, new_resource.id)

    return new_resource


@router.get(
    "/chunks/{resource_id}/status",
    response_model=kb_schemas.KBProcessingStatus,
    summary="查询文件处理状态"
)
async def get_file_processing_status(
        resource_id: str,
        db: AsyncSession = Depends(get_db)
):
    """
    查询指定文件（Resource）的切片处理进度。
    返回总切片数、待处理数、完成数、失败数以及聚合状态。
    """
    return await kb_crud.get_chunk_stats_by_resource(db, resource_id=resource_id)


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
