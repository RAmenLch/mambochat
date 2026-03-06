# backend/routers/skill_management.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, Dict
from pydantic import BaseModel, Field

from backend.database import get_db
from backend import schemas
from backend.schemas.enums import ResourceType, ResourceItemType, FileManagementType
from backend.models import resource_model
from backend.crud import resource_crud
from backend.services.file_service import FileService
from backend.utils.skills_utils import SkillValidator, build_file_node_tree
from schemas.resource import SkillCreate

router = APIRouter()


@router.post("", response_model=schemas.Resource, status_code=status.HTTP_201_CREATED, summary="新建 SKILL")
async def create_skill(skill_in: SkillCreate, db: AsyncSession = Depends(get_db)):
    """
    新建一个 SKILL 文件夹，并自动初始化包含 frontmatter 的 SKILL.md 文件。
    """
    # 1. 创建 SKILL 文件夹 Resource
    folder_create = schemas.ResourceCreate(
        name=skill_in.name,
        description=skill_in.description,
        itemType=ResourceItemType.FOLDER,
        resourceType=ResourceType.SKILL,
        parentId=skill_in.parentId,
        initial_content=None,
        initial_attributes=None
    )
    folder_res = await resource_crud.create_resource(db, folder_create)

    try:
        # 2. 在内存中拼接初始 Markdown 字符串
        md_content = f"---\nname: {skill_in.name}\ndescription: {skill_in.description}\n---\n"
        md_bytes = md_content.encode('utf-8')

        # 3. 保存文件 (FileService)
        file_service = FileService(db)
        db_file = await file_service.save_file_from_bytes(
            data=md_bytes,
            filename="SKILL.md",
            mime_type="text/markdown",
            management_type=[FileManagementType.RESOURCE.value],
            sub_path="resources"
        )

        # 4. 创建 SKILL.md 的 Resource 记录，并作为 SKILL 文件夹的子节点
        file_create = schemas.ResourceCreate(
            name="SKILL.md",
            itemType=ResourceItemType.RESOURCE,
            resourceType=ResourceType.FILE,
            parentId=folder_res.id,
            initial_content=db_file.id,
            initial_attributes={}
        )
        await resource_crud.create_resource(db, file_create)

        # 刷新 folder_res 以确保返回最新状态
        await db.refresh(folder_res)
        return folder_res

    except Exception as e:
        # 发生异常时，由于部分 CRUD 自带 commit，这里仅抛出异常，实际生产中可增加补偿删除逻辑
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to initialize SKILL.md: {str(e)}")


@router.get("/{resource_id}/validate", response_model=schemas.SkillValidationResult, summary="验证 SKILL 规范")
async def validate_skill(resource_id: str, db: AsyncSession = Depends(get_db)):
    """
    验证指定的 SKILL 文件夹是否符合 Agent Skills 规范。
    """
    # 1. 校验目标资源是否存在且类型正确
    folder_res = await resource_crud.get_resource(db, resource_id)
    if not folder_res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if folder_res.resourceType != ResourceType.SKILL.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resource is not a SKILL")

    # 2. CTE 递归查询，获取该 SKILL 文件夹及其所有子孙节点
    cte = select(resource_model.Resource).where(
        resource_model.Resource.id == resource_id
    ).cte(name="hierarchy", recursive=True)

    child = resource_model.Resource
    cte = cte.union_all(
        select(child).join(cte, child.parentId == cte.c.id)
    )

    # 关联查询最新版本信息
    stmt = select(resource_model.Resource).options(
        selectinload(resource_model.Resource.latest_version)
    ).join(cte, resource_model.Resource.id == cte.c.id)

    result = await db.execute(stmt)
    all_resources = result.scalars().all()

    # 3. 筛选出所有 FILE 节点，提取文件内容
    file_contents: Dict[str, str] = {}
    file_service = FileService(db)

    for res in all_resources:
        # 兼容判断：只要是文件类型，就尝试读取
        if res.itemType == ResourceItemType.RESOURCE.value and res.resourceType == ResourceType.FILE.value:
            if res.latest_version and res.latest_version.content:
                file_id = res.latest_version.content
                try:
                    # 使用 get_file_content 获取字节流并解码，兼容 db 和 local 存储
                    content_bytes = await file_service.get_file_content(file_id)
                    file_contents[res.id] = content_bytes.decode('utf-8')
                except Exception:
                    # 读取失败时视为空内容，由验证器统一处理
                    file_contents[res.id] = ""

    # 4. 构建 FileNode 树
    root_node = build_file_node_tree(all_resources, file_contents, resource_id)
    if not root_node:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build file node tree")

    # 5. 执行验证
    validator = SkillValidator()
    validation_result = validator.validate_tree(root_node)

    return schemas.SkillValidationResult(
        is_valid=validation_result.is_valid,
        errors=validation_result.errors,
        warnings=validation_result.warnings
    )
