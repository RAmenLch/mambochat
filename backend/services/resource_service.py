# backend/services/resource_service.py

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud import chat_crud,resource_crud
from .. import schemas
from ..models import chat_model


# 暂时为空

