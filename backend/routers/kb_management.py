# backend/routers/kb_management.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend import schemas
from backend.schemas import kb as kb_schemas
from backend.services.kb_service import KnowledgeBaseService

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
    创建一个新的知识库资源（本质上是一个特殊的文件夹）。
    需要指定 Embedding 模型 ID。
    """
    service = KnowledgeBaseService(db)
    try:
        return await service.create_knowledge_base(kb_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
