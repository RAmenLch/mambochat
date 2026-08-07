# backend/services/skill_import_service.py

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
import yaml
import httpx
from typing import List, Optional, Dict
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend import schemas
from backend.schemas.enums import ResourceItemType, ResourceType, FileManagementType
from backend.crud import resource_crud, setting_crud
from backend.services.file_service import FileService
from backend.services.resource_service import delete_resource_tree
from backend.utils.skills_utils import SkillValidator, FileNode, identify_skill_roots
from backend.utils.path_safe import RESERVED_PATH_NAMES
from backend.models import resource_model


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# ZIP 导入安全限制（均可通过环境变量调整）
MAX_ZIP_FILE_SIZE = _env_int("SKILL_MAX_ZIP_SIZE", 500 * 1024 * 1024)             # 500 MB：ZIP 文件本身大小上限
MAX_TOTAL_UNCOMPRESSED_SIZE = _env_int("SKILL_MAX_UNCOMPRESSED_SIZE", 2 * 1024 * 1024 * 1024)  # 2 GB：解压后总大小上限
MAX_ZIP_FILE_COUNT = _env_int("SKILL_MAX_ZIP_FILES", 100000)                       # ZIP 内最大文件数量
MAX_ZIP_SINGLE_FILE_SIZE = _env_int("SKILL_MAX_SINGLE_FILE_SIZE", 100 * 1024 * 1024)  # 100 MB：ZIP 内单个文件大小上限
MAX_ZIP_COMPRESSION_RATIO = _env_int("SKILL_MAX_COMPRESSION_RATIO", 200)           # 解压总量/压缩包大小 比值上限，防 ZIP 炸弹

# GitHub 下载配置
SKILL_SCAN_MAX_DEPTH = _env_int("SKILL_SCAN_MAX_DEPTH", 3)   # 容器目录（skills/ 等）内最大扫描深度
SKILL_GITHUB_MIRRORS = [m.strip().rstrip("/") for m in os.environ.get("SKILL_GITHUB_MIRROR", "").split(",") if m.strip()]
SKILL_CACHE_DIR = os.path.join(tempfile.gettempdir(), "mambochat_skill_cache")
SKILL_CACHE_TTL = _env_int("SKILL_CACHE_TTL", 3600)        # 缓存有效期（秒），默认 1 小时
SKILL_DOWNLOAD_RETRIES = max(1, _env_int("SKILL_DOWNLOAD_RETRIES", 3))
SKILL_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "MambochatSkillImporter/1.0"


class _SkillDownloadError(Exception):
    """GitHub 下载过程中的可分类错误。retryable=True 表示可重试（限流/5xx/网络）。"""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class SkillImportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.file_service = FileService(db)

    def _extract_name_from_md(self, content: bytes) -> Optional[str]:
        """尝试从 SKILL.md 内容中提前解析出 name 字段"""
        try:
            text = content.decode('utf-8')
            match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if match:
                data = yaml.safe_load(match.group(1))
                return data.get("name")
        except Exception:
            pass
        return None

    async def import_from_file(self, file: UploadFile, parent_id: Optional[str],
                               on_conflict: str = "error") -> schemas.SkillImportResponse:
        """
        处理文件/ZIP上传导入逻辑。
        """
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.TemporaryDirectory() as tmpdir:
            if suffix == '.zip':
                zip_path = os.path.join(tmpdir, "upload.zip")
                content = await self._safe_read_upload(file)
                with open(zip_path, "wb") as buffer:
                    buffer.write(content)
                self._safe_extract_zip(zip_path, tmpdir)

                # 清理压缩包防止干扰
                os.remove(zip_path)

                # 直接处理 tmpdir，内部相对路径会自动生成正确的目录结构
                return await self._process_directory(tmpdir, parent_id, on_conflict)

            elif file.filename == "SKILL.md":
                content = await file.read()

                # 提前解析 name，以此作为目录名，避免 skill_root 校验报错
                frontmatter_name = self._extract_name_from_md(content)
                if not frontmatter_name:
                    frontmatter_name = "unnamed_skill"

                safe_name = self._sanitize_name(frontmatter_name)
                skill_dir = os.path.join(tmpdir, safe_name)
                os.makedirs(skill_dir)

                skill_md_path = os.path.join(skill_dir, "SKILL.md")
                with open(skill_md_path, "wb") as buffer:
                    buffer.write(content)

                return await self._process_directory(tmpdir, parent_id, on_conflict)

            else:
                raise HTTPException(status_code=400,
                                    detail="Invalid file type. Please upload a ZIP file or a single SKILL.md file.")

    async def _get_proxy_config(self) -> Optional[str]:
        """读取全局代理配置，未启用时返回 None。"""
        proxy_setting = await setting_crud.get_setting(self.db, "proxy_enabled")
        if proxy_setting and proxy_setting.value == "True":
            url_setting = await setting_crud.get_setting(self.db, "proxy_url")
            if url_setting and url_setting.value:
                return url_setting.value
        return None

    def _parse_github_source(self, source: str) -> tuple:
        """
        解析 GitHub 来源，支持：
        - https://github.com/owner/repo(.git)(/path)
        - github.com/owner/repo
        - owner/repo（npx skills 简写）
        - npx skills add owner/repo [options]
        - git@github.com:owner/repo.git / ssh://git@github.com/owner/repo.git
        返回 (owner, repo)；无法解析时抛 400。
        """
        text = source.strip()

        # 1. npx skills add <source> [options...]
        match = re.match(r"^npx\s+skills\s+add\s+([^\s]+)", text, re.IGNORECASE)
        if match:
            text = match.group(1)

        # 2. SSH: git@github.com:owner/repo.git 或 ssh://git@github.com/owner/repo.git
        match = re.match(r"^(?:git@|ssh://git@)[^/:]+[:/]([^/]+)/([^/]+?)(?:\.git)?$", text)
        if match:
            return match.group(1), match.group(2)

        # 3. URL: (https?://)(www.)github.com/owner/repo(.git)(/anything)
        match = re.match(
            r"^(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$",
            text, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)

        # 4. 简写: owner/repo（可带 .git；忽略 @skill 过滤，本项目为全量导入）
        match = re.match(r"^([^/\s]+)/([^/\s]+?)(?:@[^\s/]+)?$", text)
        if match:
            return match.group(1), match.group(2).removesuffix(".git")

        raise HTTPException(
            status_code=400,
            detail="无法识别的 GitHub 来源，支持：仓库 URL、owner/repo、npx skills add owner/repo"
        )

    def _build_download_urls(self, owner: str, repo: str) -> List[str]:
        """构建下载源列表：codeload 直连 → github.com archive → 可配置镜像。"""
        urls = [
            f"https://codeload.github.com/{owner}/{repo}/zip/HEAD",
            f"https://github.com/{owner}/{repo}/archive/HEAD.zip",
        ]
        for mirror in SKILL_GITHUB_MIRRORS:
            urls.append(f"{mirror}/https://github.com/{owner}/{repo}/archive/HEAD.zip")
        return urls

    def _build_client_plan(self, proxy_url: Optional[str]) -> List[tuple]:
        """
        构建 (label, proxy, trust_env) 客户端计划。
        配置了代理时依次尝试：显式代理 → 真直连；未配置时信任系统环境（含系统代理）。
        """
        if proxy_url:
            return [("proxy", proxy_url, False), ("direct", None, False)]
        return [("system", None, True)]

    async def _stream_download(self, client: httpx.AsyncClient, url: str, target_path: str) -> None:
        """流式下载单个源到目标文件，带大小上限；失败抛 _SkillDownloadError。"""
        try:
            async with client.stream("GET", url, follow_redirects=True) as resp:
                if resp.status_code == 404:
                    raise _SkillDownloadError("仓库不存在或不可访问 (HTTP 404)")
                if resp.status_code in (403, 429):
                    raise _SkillDownloadError(
                        f"GitHub 请求被拒绝（限流或风控）(HTTP {resp.status_code})", retryable=True)
                if resp.status_code >= 500:
                    raise _SkillDownloadError(f"GitHub 服务器错误 (HTTP {resp.status_code})", retryable=True)
                resp.raise_for_status()

                total = 0
                with open(target_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_ZIP_FILE_SIZE:
                            raise _SkillDownloadError(
                                f"下载的 ZIP 超过大小上限（{MAX_ZIP_FILE_SIZE // 1024 // 1024} MB），"
                                f"可通过环境变量 SKILL_MAX_ZIP_SIZE 调整")
                        f.write(chunk)
        except httpx.TimeoutException as e:
            raise _SkillDownloadError("连接或读取超时", retryable=True) from e
        except httpx.HTTPStatusError as e:
            raise _SkillDownloadError(f"HTTP {e.response.status_code}", retryable=False) from e
        except httpx.TransportError as e:
            raise _SkillDownloadError(f"网络错误: {type(e).__name__}", retryable=True) from e

    async def _download_with_retry(self, proxy: Optional[str], trust_env: bool,
                                   url: str, target_path: str) -> None:
        """单个下载源 + 单个客户端的指数退避重试。"""
        last_error: Optional[_SkillDownloadError] = None
        for attempt in range(SKILL_DOWNLOAD_RETRIES):
            try:
                async with httpx.AsyncClient(
                        proxy=proxy, timeout=SKILL_DOWNLOAD_TIMEOUT, trust_env=trust_env,
                        headers={"User-Agent": USER_AGENT}) as client:
                    await self._stream_download(client, url, target_path)
                return
            except _SkillDownloadError as e:
                if not e.retryable:
                    raise
                last_error = e
                if attempt < SKILL_DOWNLOAD_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
        raise last_error

    async def _download_repo_zip(self, owner: str, repo: str,
                                 proxy_url: Optional[str], target_path: str) -> None:
        """按 源 × 客户端 顺序尝试下载，全部失败时抛出聚合错误。"""
        errors: List[str] = []
        for url in self._build_download_urls(owner, repo):
            for label, proxy, trust_env in self._build_client_plan(proxy_url):
                try:
                    await self._download_with_retry(proxy, trust_env, url, target_path)
                    return
                except _SkillDownloadError as e:
                    errors.append(f"[{label}] {url}: {e.message}")
        detail = "\n".join([
            f"从 GitHub 下载仓库 {owner}/{repo} 失败，已尝试以下方式：",
            *errors,
            "建议：检查网络连接，或在设置中开启代理后重试。",
        ])
        raise HTTPException(status_code=400, detail=detail)

    def _cache_zip_path(self, owner: str, repo: str) -> str:
        return os.path.join(SKILL_CACHE_DIR, f"{owner}_{repo}.zip")

    async def _load_cached_zip(self, owner: str, repo: str) -> Optional[str]:
        """命中且未过期的缓存返回 zip 路径，否则返回 None；任何异常静默降级。"""
        try:
            zip_path = self._cache_zip_path(owner, repo)
            meta_path = zip_path + ".meta"
            if not (os.path.exists(zip_path) and os.path.exists(meta_path)):
                return None
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if time.time() - meta.get("downloaded_at", 0) > SKILL_CACHE_TTL:
                return None
            if os.path.getsize(zip_path) > MAX_ZIP_FILE_SIZE:
                return None
            return zip_path
        except Exception:
            return None

    def _save_cache(self, owner: str, repo: str, zip_path: str) -> None:
        """将下载的 zip 写入缓存；失败静默降级。"""
        try:
            os.makedirs(SKILL_CACHE_DIR, exist_ok=True)
            dest = self._cache_zip_path(owner, repo)
            shutil.copyfile(zip_path, dest)
            with open(dest + ".meta", "w", encoding="utf-8") as f:
                json.dump({"downloaded_at": time.time(), "size": os.path.getsize(zip_path)}, f)
        except Exception:
            pass

    async def import_from_github(self, repo_url: str, parent_id: Optional[str],
                                 on_conflict: str = "error") -> schemas.SkillImportResponse:
        """
        处理 GitHub 仓库导入逻辑。
        不使用 GitHub REST API（避免限流），通过 archive/HEAD.zip 固定入口下载，
        支持多源回退、代理、重试、流式下载与本地缓存。
        """
        proxy_url = await self._get_proxy_config()

        # Parse GitHub source（支持 URL / owner-repo 简写 / npx skills add 命令 / SSH 格式）
        owner, repo = self._parse_github_source(repo_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            cached_zip = await self._load_cached_zip(owner, repo)
            if cached_zip:
                self._safe_extract_zip(cached_zip, tmpdir)
            else:
                zip_path = os.path.join(tmpdir, "repo.zip")
                await self._download_repo_zip(owner, repo, proxy_url, zip_path)
                self._save_cache(owner, repo, zip_path)
                self._safe_extract_zip(zip_path, tmpdir)
                os.remove(zip_path)

            # GitHub zip typically extracts to a folder like repo-branch
            extracted_items = os.listdir(tmpdir)
            extracted_dir = None
            for item in extracted_items:
                if os.path.isdir(os.path.join(tmpdir, item)):
                    extracted_dir = os.path.join(tmpdir, item)
                    break

            if not extracted_dir:
                raise HTTPException(status_code=500, detail="Failed to locate extracted directory.")

            return await self._process_directory(extracted_dir, parent_id, on_conflict)

    async def _process_directory(self, disk_root: str, parent_id: Optional[str],
                                 on_conflict: str = "error") -> schemas.SkillImportResponse:
        """
        核心处理逻辑：识别、校验、创建资源。
        扁平化导入：Skill 直接挂在 parent_id 下；同名冲突按 on_conflict 策略处理。
        """
        # 1. Identify Skill Roots（容器语义：根 1 层 + skills/、$X/skills/ 内 max_depth 层，同名浅层优先）
        skill_dirs = identify_skill_roots(disk_root, SKILL_SCAN_MAX_DEPTH)

        details = []
        success_count = 0
        failed_count = 0
        skipped_count = 0

        if not skill_dirs:
            return schemas.SkillImportResponse(
                total_detected=0,
                success_count=0,
                failed_count=0,
                details=[schemas.SkillImportResultItem(name="N/A", status="failed", error="No valid SKILL.md found.")]
            )

        # 2. 解析 + 校验 + 预检同名冲突（error 模式下一个都不创建，避免半成品）
        pending = []  # (skill_abs_path, frontmatter_name, safe_name, existing)
        conflict_names = []
        for skill_abs_path in skill_dirs:
            skill_name = os.path.basename(skill_abs_path)

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

            safe_name = self._sanitize_name(frontmatter_name)
            existing = await self._find_existing_skill(safe_name, parent_id)
            pending.append((skill_abs_path, frontmatter_name, safe_name, existing))
            if existing:
                conflict_names.append(safe_name)

        if conflict_names and on_conflict == "error":
            raise HTTPException(
                status_code=409,
                detail=f"检测到同名 Skill: {', '.join(conflict_names)}。请选择覆盖或跳过。"
            )

        # 3. Process each Skill
        for skill_abs_path, frontmatter_name, safe_name, existing in pending:
            try:
                if existing:
                    if on_conflict == "skip":
                        skipped_count += 1
                        details.append(schemas.SkillImportResultItem(
                            name=frontmatter_name,
                            status="skipped",
                            error="同名 Skill 已存在，已跳过"
                        ))
                        continue
                    # overwrite: 删除旧资源树后重建
                    await delete_resource_tree(self.db, existing.id)

                skill_resource = await self._create_skill_resources(safe_name, parent_id)

                # Create files inside Skill
                await self._create_files_recursive(skill_abs_path, skill_resource.id)

                success_count += 1
                details.append(schemas.SkillImportResultItem(
                    name=frontmatter_name,
                    status="success",
                    resource_id=skill_resource.id
                ))
            except Exception as e:
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
            skipped_count=skipped_count,
            details=details
        )

    async def _find_existing_skill(self, name: str, parent_id: Optional[str]) -> Optional[resource_model.Resource]:
        """在 parent_id 下查找同名资源（parent_id 为 None 或 "root" 时查根目录）。"""
        normalized_parent_id = None if parent_id == "root" else parent_id
        return await resource_crud.get_resource_by_name_and_parent(self.db, name, normalized_parent_id)

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

    async def _create_skill_resources(self, safe_skill_name: str, root_parent_id: Optional[str]) -> resource_model.Resource:
        """
        扁平化创建 Skill 文件夹资源，直接挂在 root_parent_id 下。
        调用方已保证无同名冲突。
        """
        skill_schema = schemas.ResourceCreate(
            name=safe_skill_name,
            itemType=ResourceItemType.FOLDER,
            resourceType=ResourceType.SKILL,
            parentId=root_parent_id
        )
        return await resource_crud.create_resource(self.db, skill_schema)

    async def _create_files_recursive(self, disk_path: str, resource_parent_id: str):
        """递归创建文件资源"""
        for item in os.listdir(disk_path):
            item_path = os.path.join(disk_path, item)
            if os.path.isfile(item_path):
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
                safe_item_name = self._sanitize_name(item)
                folder_schema = schemas.ResourceCreate(
                    name=safe_item_name,
                    itemType=ResourceItemType.FOLDER,
                    parentId=resource_parent_id
                )
                sub_folder = await resource_crud.create_resource(self.db, folder_schema)
                await self._create_files_recursive(item_path, sub_folder.id)

    def _sanitize_name(self, name: str) -> str:
        """清理非法字符并处理系统保留字冲突。"""
        safe = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
        # 如果清理后的名称是系统保留字，追加后缀避免冲突
        if safe.lower() in RESERVED_PATH_NAMES:
            safe = f"{safe}_folder"
        return safe

    async def _safe_read_upload(self, file: UploadFile) -> bytes:
        """安全读取上传文件内容，校验大小上限。"""
        content = b""
        while True:
            chunk = await file.read(1024 * 1024)  # 每次读 1MB
            if not chunk:
                break
            content += chunk
            if len(content) > MAX_ZIP_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大（{len(content) // 1024 // 1024} MB），上限为 {MAX_ZIP_FILE_SIZE // 1024 // 1024} MB。"
                )
        return content

    def _safe_extract_zip(self, zip_path: str, target_dir: str) -> None:
        """安全解压 ZIP，防止 ZIP 炸弹与路径穿越攻击。"""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            infos = zip_ref.infolist()

            # 检查文件数量
            if len(infos) > MAX_ZIP_FILE_COUNT:
                raise HTTPException(
                    status_code=413,
                    detail=f"ZIP 文件包含过多条目（{len(infos)}），上限为 {MAX_ZIP_FILE_COUNT}。"
                )

            # 检查总解压大小
            total_uncompressed = sum(info.file_size for info in infos if not info.is_dir())
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"ZIP 解压后总大小过大（{total_uncompressed // 1024 // 1024} MB），上限为 {MAX_TOTAL_UNCOMPRESSED_SIZE // 1024 // 1024} MB。"
                )

            # 压缩比检测：高膨胀比是 ZIP 炸弹的典型特征
            zip_size = os.path.getsize(zip_path)
            if zip_size > 0 and total_uncompressed / zip_size > MAX_ZIP_COMPRESSION_RATIO:
                raise HTTPException(
                    status_code=413,
                    detail=f"ZIP 压缩比异常（{total_uncompressed // zip_size}:1），疑似 ZIP 炸弹，已拒绝解压。"
                           f"可通过环境变量 SKILL_MAX_COMPRESSION_RATIO 调整。"
                )

            # 检查单个文件大小与路径安全
            for info in infos:
                if not info.is_dir() and info.file_size > MAX_ZIP_SINGLE_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"ZIP 内单个文件过大: {info.filename}（{info.file_size // 1024 // 1024} MB），"
                               f"上限为 {MAX_ZIP_SINGLE_FILE_SIZE // 1024 // 1024} MB。"
                    )
                normalized = info.filename.replace("\\", "/")
                if normalized.startswith("/") or re.match(r"^[a-zA-Z]:/", normalized) \
                        or ".." in normalized.split("/"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"ZIP 包含不安全路径: {info.filename}"
                    )

            zip_ref.extractall(target_dir)
