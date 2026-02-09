# backend/routers/file_management.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.storage_service import storage_service, LocalStorageService
from backend.database import get_db
from backend.crud import file_crud
from backend import schemas
from backend.schemas.enums import FileManagementType

router = APIRouter(
    prefix="/api/files",
    tags=["File Management"]
)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# =============================================
# 明确允许的非文本 MIME 类型白名单
# 所有 text/* 类型通过 is_mime_type_allowed() 通用放行
# =============================================
ALLOWED_MIME_TYPES = {
    # --- 图片 ---
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/svg+xml", "image/bmp", "image/tiff", "image/heic", "image/heif",

    # --- 音频 ---
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/webm",
    "audio/mp4", "audio/flac", "audio/aac",

    # --- 视频 ---
    "video/mp4", "video/webm", "video/quicktime",
    "video/x-msvideo", "video/x-matroska",

    # --- 文档 ---
    "application/pdf", "application/rtf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",

    # --- 文本类 application/* (不以 text/ 开头但本质是文本) ---
    "application/json", "application/xml", "application/sql",
    "application/javascript", "application/x-sh",
    "application/x-yaml", "application/x-ipynb+json",
}

# =============================================
# 文件扩展名 → MIME 类型映射（修正 octet-stream 用）
# =============================================
TEXT_EXTENSION_MIME_MAP = {
    # 通用文本
    ".txt": "text/plain", ".log": "text/plain", ".md": "text/markdown",
    ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".rst": "text/x-rst", ".tex": "text/x-tex", ".adoc": "text/x-asciidoc",

    # Web 基础
    ".html": "text/html", ".htm": "text/html", ".css": "text/css",
    ".scss": "text/x-scss", ".sass": "text/x-sass", ".less": "text/x-less",

    # JavaScript / TypeScript
    ".js": "application/javascript", ".mjs": "application/javascript",
    ".cjs": "application/javascript", ".jsx": "application/javascript",
    ".ts": "text/typescript", ".tsx": "text/typescript",

    # 数据 / 配置
    ".json": "application/json", ".jsonl": "application/json",
    ".xml": "application/xml", ".svg": "image/svg+xml",
    ".yaml": "text/yaml", ".yml": "text/yaml",
    ".toml": "text/x-toml", ".ini": "text/x-ini",
    ".cfg": "text/x-ini", ".conf": "text/plain",
    ".env": "text/plain", ".properties": "text/x-java-properties",
    ".plist": "application/xml",

    # 系统编程语言
    ".c": "text/x-c", ".h": "text/x-c",
    ".cpp": "text/x-c++src", ".cxx": "text/x-c++src",
    ".cc": "text/x-c++src", ".hpp": "text/x-c++src",
    ".rs": "text/x-rust", ".go": "text/x-go",
    ".swift": "text/x-swift", ".m": "text/x-objective-c",
    ".zig": "text/x-zig", ".nim": "text/x-nim",
    ".v": "text/x-v", ".d": "text/x-d",

    # JVM 系列
    ".java": "text/x-java-source", ".kt": "text/x-kotlin",
    ".kts": "text/x-kotlin", ".scala": "text/x-scala",
    ".groovy": "text/x-groovy", ".gradle": "text/x-gradle",
    ".clj": "text/x-clojure", ".cljs": "text/x-clojure",

    # .NET 系列
    ".cs": "text/x-csharp", ".fs": "text/x-fsharp", ".vb": "text/x-vb",

    # 脚本语言
    ".py": "text/x-python", ".pyw": "text/x-python",
    ".pyi": "text/x-python", ".pyx": "text/x-python",
    ".rb": "text/x-ruby", ".rake": "text/x-ruby",
    ".pl": "text/x-perl", ".pm": "text/x-perl",
    ".php": "text/x-php",
    ".lua": "text/x-lua",
    ".r": "text/x-r",
    ".jl": "text/x-julia",
    ".dart": "text/x-dart",
    ".ex": "text/x-elixir", ".exs": "text/x-elixir",
    ".erl": "text/x-erlang", ".hrl": "text/x-erlang",
    ".hs": "text/x-haskell", ".lhs": "text/x-haskell",
    ".ml": "text/x-ocaml", ".mli": "text/x-ocaml",
    ".lisp": "text/x-lisp", ".el": "text/x-lisp",
    ".scm": "text/x-scheme", ".rkt": "text/x-racket",
    ".tcl": "text/x-tcl", ".awk": "text/x-awk",

    # Shell
    ".sh": "application/x-sh", ".bash": "application/x-sh",
    ".zsh": "application/x-sh", ".fish": "text/x-fish",
    ".ps1": "text/x-powershell", ".psm1": "text/x-powershell",
    ".bat": "text/x-batch", ".cmd": "text/x-batch",

    # 数据库
    ".sql": "application/sql",

    # 前端框架 / 模板
    ".vue": "text/x-vue", ".svelte": "text/x-svelte",
    ".ejs": "text/x-ejs", ".hbs": "text/x-handlebars",
    ".pug": "text/x-pug", ".erb": "text/x-erb",
    ".j2": "text/x-jinja", ".jinja": "text/x-jinja",
    ".jinja2": "text/x-jinja", ".mustache": "text/x-mustache",

    # DevOps / 构建
    ".dockerfile": "text/x-dockerfile",
    ".cmake": "text/x-cmake",
    ".tf": "text/x-terraform", ".tfvars": "text/x-terraform",
    ".nix": "text/x-nix",

    # 接口定义
    ".proto": "text/x-protobuf",
    ".graphql": "text/x-graphql", ".gql": "text/x-graphql",

    # Notebook
    ".ipynb": "application/x-ipynb+json",

    # 杂项
    ".rtf": "application/rtf",
}

# 无扩展名特殊文件名 → MIME 映射
_TEXT_FILENAME_MAP = {
    "dockerfile": "text/x-dockerfile",
    "makefile": "text/x-makefile",
    "gnumakefile": "text/x-makefile",
    "jenkinsfile": "text/x-groovy",
    "vagrantfile": "text/x-ruby",
    "rakefile": "text/x-ruby",
    "gemfile": "text/x-ruby",
    "procfile": "text/plain",
    "justfile": "text/plain",
}


# =============================================
# 核心工具函数
# =============================================

async def _sniff_is_text(file: UploadFile, sample_size: int = 8192) -> bool:
    """
    通过读取文件头部样本判断是否为文本文件。
    - 空文件视为文本
    - 包含 NULL 字节 (0x00) → 二进制
    - UTF-8 解码成功 → 文本
    读取后会将文件指针重置到起始位置。
    """
    chunk = await file.read(sample_size)
    await file.seek(0)

    if not chunk:
        return True
    if b'\x00' in chunk:
        return False
    try:
        chunk.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False


def is_mime_type_allowed(mime_type: str) -> bool:
    """
    判断 MIME 类型是否允许上传。
    - 在明确白名单中 → 允许
    - 以 text/ 开头  → 允许（通用放行所有文本类型）
    - 否则 → 拒绝
    """
    if mime_type in ALLOWED_MIME_TYPES:
        return True
    if mime_type.startswith("text/"):
        return True
    return False


async def correct_mime_type(file: UploadFile) -> str:
    """
    修正文件的 MIME 类型，核心三级回退策略：

    1. .ts 特殊处理（TypeScript vs MPEG-TS 视频流）
    2. 浏览器已给出非 octet-stream 的类型 → 直接信任
    3. 对 application/octet-stream 执行：
       a. 文件扩展名映射
       b. 无扩展名文件名映射（Dockerfile / Makefile 等）
       c. 内容嗅探（检测 NULL 字节 + UTF-8 解码）→ 文本则返回 text/plain
       d. 确认二进制 → 保持 application/octet-stream
    """
    original_content_type = file.content_type or "application/octet-stream"
    filename = file.filename or ""
    filename_lower = filename.lower()

    # 获取扩展名
    ext = ""
    if "." in filename_lower:
        ext = "." + filename_lower.rsplit(".", 1)[-1]

    # ---- 特殊处理 .ts ----
    if ext == ".ts":
        if await _sniff_is_text(file):
            return "text/typescript"
        return original_content_type

    # ---- 非 octet-stream 直接返回 ----
    if original_content_type != "application/octet-stream":
        return original_content_type

    # ---- 以下处理 application/octet-stream ----

    # a. 扩展名映射
    if ext and ext in TEXT_EXTENSION_MIME_MAP:
        return TEXT_EXTENSION_MIME_MAP[ext]

    # b. 无扩展名文件名映射
    if not ext and filename_lower in _TEXT_FILENAME_MAP:
        return _TEXT_FILENAME_MAP[filename_lower]

    # c. 内容嗅探
    if await _sniff_is_text(file):
        return "text/plain"

    # d. 真的是二进制
    return original_content_type


# =============================================
# 路由
# =============================================

@router.post(
    "/upload",
    response_model=schemas.File,
    summary="上传临时文件"
)
async def upload_temporary_file(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大。最大允许 {MAX_FILE_SIZE // 1024 // 1024} MB。"
        )

    # 获取修正后的 MIME 类型
    final_mime_type = await correct_mime_type(file)

    if not is_mime_type_allowed(final_mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {final_mime_type}。"
        )

    try:
        storage_path = await storage_service.save(file, sub_path="chat_attachments")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件存储失败: {e}"
        )

    db_file = await file_crud.create_file(
        db=db,
        filename=file.filename,
        storage_path=storage_path,
        mime_type=final_mime_type,
        size=file.size,
        management_type=[FileManagementType.TEMPORARY.value]
    )

    return schemas.File(
        id=db_file.id,
        filename=db_file.filename,
        mime_type=db_file.mime_type,
        size=db_file.size,
        created_at=db_file.created_at,
        url=storage_service.get_url(db_file.storage_path)
    )


@router.get(
    "/download/{storage_path:path}",
    summary="获取/下载文件",
    responses={
        200: {"content": {"image/*": {}, "application/octet-stream": {}}},
        404: {"description": "File not found"},
    }
)
async def download_file(storage_path: str, db: AsyncSession = Depends(get_db)):
    """
    根据文件的存储路径提供文件访问，并使用原始文件名进行下载。
    """
    db_file = await file_crud.get_file_by_storage_path(db, path=storage_path)
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found in database."
        )

    if not isinstance(storage_service, LocalStorageService):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Download not implemented for the current storage service type."
        )

    base_path = storage_service.base_path.resolve()
    file_path = (base_path / db_file.storage_path).resolve()

    if not str(file_path).startswith(str(base_path)) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found or access forbidden."
        )

    return FileResponse(
        path=file_path,
        media_type=db_file.mime_type,
        filename=db_file.filename
    )
