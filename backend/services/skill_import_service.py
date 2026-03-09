# backend/services/skill_import_service.py

import os
import re
import zipfile
import tempfile
import shutil
import yaml
import httpx
from typing import List, Optional, Dict
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.schemas.enums import ResourceItemType, ResourceType, FileManagementType
from backend.crud import resource_crud, setting_crud
from backend.services.file_service import FileService
from backend.utils.skills_utils import SkillValidator, FileNode, identify_skill_roots
from backend.models import resource_model

class SkillImportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    async def import_from_file(self, file: UploadFile, parent_id: Optional[str]) -> schemas.SkillImportResponse:
        """
        处理文件/ZIP上传导入逻辑。
        """
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.TemporaryDirectory() as tmpdir:
            if suffix == '.zip':
                zip_path = os.path.join(tmpdir, "upload.zip")
                with open(zip_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)

                root_name = os.path.splitext(file.filename)[0]
                return await self._process_directory(tmpdir, root_name, parent_id)

            elif file.filename == "SKILL.md":
                skill_dir = os.path.join(tmpdir, "skill_root")
                os.makedirs(skill_dir)
                skill_md_path = os.path.join(skill_dir, "SKILL.md")
                content = await file.read()
                with open(skill_md_path, "wb") as buffer:
                    buffer.write(content)

                root_name = "skill_root"
                return await self._process_directory(tmpdir, root_name, parent_id)

            else:
                raise HTTPException(status_code=400,
                                    detail="Invalid file type. Please upload a ZIP file or a single SKILL.md file.")

    async def import_from_github(self, repo_url: str, parent_id: Optional[str]) -> schemas.SkillImportResponse:
        """
        处理 GitHub 仓库导入逻辑。
        """
        proxy_url = None
        proxy_setting = await setting_crud.get_setting(self.db, "proxy_enabled")
        if proxy_setting and proxy_setting.value == "True":
            url_setting = await setting_crud.get_setting(self.db, "proxy_url")
            proxy_url = url_setting.value if url_setting else None

        # Parse URL
        match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL format.")

        owner, repo = match.group(1), match.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]

        async with httpx.AsyncClient(proxy=proxy_url, timeout=30.0) as client:
            # Get default branch
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            try:
                resp = await client.get(api_url)
                resp.raise_for_status()
                repo_data = resp.json()
                default_branch = repo_data.get("default_branch", "main")
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch repo info: {e.response.status_code}")

            # Download ZIP
            zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{default_branch}.zip"
            try:
                resp = await client.get(zip_url, follow_redirects=True)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=400, detail=f"Failed to download repository: {e.response.status_code}")

            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "repo.zip")
                with open(zip_path, "wb") as buffer:
                    buffer.write(resp.content)

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)

                # GitHub zip typically extracts to a folder like repo-branch
                extracted_items = os.listdir(tmpdir)
                extracted_dir = None
                for item in extracted_items:
                    if os.path.isdir(os.path.join(tmpdir, item)):
                        extracted_dir = os.path.join(tmpdir, item)
                        break

                if not extracted_dir:
                    raise HTTPException(status_code=500, detail="Failed to locate extracted directory.")

                root_name = f"{owner}_{repo}"
                return await self._process_directory(extracted_dir, root_name, parent_id)

    async def _process_directory(self, disk_root: str, root_name: str,
                                 parent_id: Optional[str]) -> schemas.SkillImportResponse:
        """
        核心处理逻辑：识别、校验、创建资源。
        """
        # 1. Identify Skill Roots
        skill_dirs = identify_skill_roots(disk_root)

        details = []
        success_count = 0
        failed_count = 0

        if not skill_dirs:
            return schemas.SkillImportResponse(
                total_detected=0,
                success_count=0,
                failed_count=0,
                details=[schemas.SkillImportResultItem(name="N/A", status="failed", error="No valid SKILL.md found.")]
            )

        # 2. Create Root Folder (Container)
        # Sanitize name
        safe_root_name = self._sanitize_name(root_name)

        # Check conflict for root folder
        existing_names = await resource_crud.get_child_names_by_parent_id(self.db, parent_id)
        if safe_root_name in existing_names:
            raise HTTPException(status_code=400,
                                detail=f"Root folder name conflict: '{safe_root_name}' already exists in target location.")

        root_folder_schema = schemas.ResourceCreate(
            name=safe_root_name,
            itemType=ResourceItemType.FOLDER,
            parentId=parent_id
        )
        root_folder_res = await resource_crud.create_resource(self.db, root_folder_schema)

        # 3. Process each Skill
        for skill_abs_path in skill_dirs:
            skill_name = os.path.basename(skill_abs_path)
            relative_path = os.path.relpath(skill_abs_path, disk_root)

            # Validate Skill
            validation_result = await self._validate_skill_on_disk(skill_abs_path)

            if not validation_result.is_valid:
                failed_count += 1
                details.append(schemas.SkillImportResultItem(
                    name=skill_name,
                    status="failed",
                    error="; ".join(validation_result.errors)
                ))
                continue

            # Extract name from SKILL.md frontmatter to ensure consistency
            frontmatter_name = await self._get_skill_name(skill_abs_path)
            if not frontmatter_name:
                failed_count += 1
                details.append(schemas.SkillImportResultItem(
                    name=skill_name,
                    status="failed",
                    error="Could not parse name from SKILL.md"
                ))
                continue

            try:
                # Create intermediate folders and Skill folder
                skill_resource = await self._create_skill_resources(relative_path, root_folder_res.id, frontmatter_name)

                # Create files inside Skill
                await self._create_files_recursive(skill_abs_path, skill_resource.id)

                success_count += 1
                details.append(schemas.SkillImportResultItem(
                    name=frontmatter_name,
                    status="success",
                    resource_id=skill_resource.id
                ))
            except Exception as e:
                # Note: Since FileService commits immediately, we might have orphan files if this step fails midway.
                # But as per requirement, we rely on the orphan cleaner.
                failed_count += 1
                details.append(schemas.SkillImportResultItem(
                    name=frontmatter_name,
                    status="failed",
                    error=str(e)
                ))

        return schemas.SkillImportResponse(
            total_detected=len(skill_dirs),
            success_count=success_count,
            failed_count=failed_count,
            details=details
        )

    async def _validate_skill_on_disk(self, skill_dir: str) -> schemas.SkillValidationResult:
        """构建文件树并校验"""
        validator = SkillValidator()
        root_node = await self._build_file_node_from_disk(skill_dir)
        if not root_node:
            return schemas.SkillValidationResult(is_valid=False, errors=["Failed to build file tree"], warnings=[])
        return validator.validate_tree(root_node)

    async def _build_file_node_from_disk(self, path: str) -> Optional[FileNode]:
        """递归构建内存文件树"""
        if not os.path.exists(path):
            return None

        name = os.path.basename(path)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return FileNode(type="file", name=name, content=content)
        else:
            children = []
            for item in os.listdir(path):
                child_path = os.path.join(path, item)
                child_node = await self._build_file_node_from_disk(child_path)
                if child_node:
                    children.append(child_node)
            return FileNode(type="dir", name=name, children=children)

    async def _get_skill_name(self, skill_dir: str) -> Optional[str]:
        md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(md_path):
            return None
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if match:
                try:
                    data = yaml.safe_load(match.group(1))
                    return data.get("name")
                except:
                    return None
        return None

    async def _create_skill_resources(self, relative_path: str, root_parent_id: str,
                                      skill_name: str) -> resource_model.Resource:
        """
        根据相对路径创建中间文件夹，最后创建 Skill 文件夹。
        """
        parts = relative_path.split(os.sep)
        current_parent_id = root_parent_id

        # Create intermediate folders
        if len(parts) > 1:
            for folder_name in parts[:-1]:
                safe_name = self._sanitize_name(folder_name)
                # Check if exists
                children = await resource_crud.get_resources_by_parent_ids(self.db, [current_parent_id])
                existing = next((c for c in children if c.name == safe_name), None)

                if existing:
                    current_parent_id = existing.id
                else:
                    folder_schema = schemas.ResourceCreate(
                        name=safe_name,
                        itemType=ResourceItemType.FOLDER,
                        parentId=current_parent_id
                    )
                    new_folder = await resource_crud.create_resource(self.db, folder_schema)
                    current_parent_id = new_folder.id

        # Create Skill Folder
        safe_skill_name = self._sanitize_name(skill_name)

        # Check conflict
        existing_names = await resource_crud.get_child_names_by_parent_id(self.db, current_parent_id)
        if safe_skill_name in existing_names:
            # Conflict handling logic: if exists, we might append suffix or fail.
            # Plan says: "Check conflict... if conflict mark failed".
            # But here we are inside a loop, we should raise to let outer loop catch it.
            raise ValueError(f"Skill name conflict: '{safe_skill_name}' already exists in the destination.")

        skill_schema = schemas.ResourceCreate(
            name=safe_skill_name,
            itemType=ResourceItemType.FOLDER,
            resourceType=ResourceType.SKILL,
            parentId=current_parent_id
        )
        return await resource_crud.create_resource(self.db, skill_schema)

    async def _create_files_recursive(self, disk_path: str, resource_parent_id: str):
        """递归创建文件资源"""
        for item in os.listdir(disk_path):
            item_path = os.path.join(disk_path, item)
            if os.path.isfile(item_path):
                # Skip SKILL.md as it is represented by the folder itself (metadata wise)
                # But technically we should store it as a file resource if the system treats files as resources.
                # Based on existing logic: SKILL folder contains SKILL.md as a file resource.

                with open(item_path, "rb") as f:
                    content_bytes = f.read()

                db_file = await self.file_service.save_file_from_bytes(
                    data=content_bytes,
                    filename=item,
                    mime_type="text/markdown" if item.endswith(".md") else "application/octet-stream",
                    management_type=[FileManagementType.RESOURCE.value],
                    sub_path="skills"
                )

                file_res_schema = schemas.ResourceCreate(
                    name=item,
                    itemType=ResourceItemType.RESOURCE,
                    resourceType=ResourceType.FILE,
                    parentId=resource_parent_id,
                    initial_content=db_file.id,
                    initial_attributes={}
                )
                await resource_crud.create_resource(self.db, file_res_schema)

            elif os.path.isdir(item_path):
                # Create sub-folder
                folder_schema = schemas.ResourceCreate(
                    name=item,
                    itemType=ResourceItemType.FOLDER,
                    parentId=resource_parent_id
                )
                sub_folder = await resource_crud.create_resource(self.db, folder_schema)
                await self._create_files_recursive(item_path, sub_folder.id)

    def _sanitize_name(self, name: str) -> str:
        # Remove or replace invalid characters
        return re.sub(r'[\\/*?:"<>|]', "_", name).strip()
