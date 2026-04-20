# backend/utils/file_utils.py

import charset_normalizer

# =============================================
# 明确允许的非文本 MIME 类型白名单
# 所有 text/* 类型通过 is_allowed_mime_type() 通用放行
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

# 已知的文本类 application/* 类型
_KNOWN_TEXT_APPLICATION_TYPES = {
    "application/json", "application/xml", "application/sql",
    "application/javascript", "application/x-sh", "application/x-yaml",
    "application/rtf", "application/x-ipynb+json",
}


class FileUtils:
    """
    文件处理核心静态工具类，集中处理所有文件的识别与转码逻辑。
    """

    @staticmethod
    def _sniff_is_text(data_sample: bytes) -> bool:
        """
        通过样本数据嗅探是否为文本文件。
        """
        if not data_sample:
            return True
        if b'\x00' in data_sample:
            return False

        try:
            data_sample.decode('utf-8')
            return True
        except UnicodeDecodeError:
            # 使用 charset-normalizer 进一步确认是否为其他编码的文本
            match = charset_normalizer.from_bytes(data_sample).best()
            return match is not None

    @staticmethod
    def correct_mime_type(filename: str, original_mime: str, data_sample: bytes) -> str:
        """
        修正文件的 MIME 类型，核心三级回退策略。
        """
        original_mime = original_mime or "application/octet-stream"
        filename = filename or ""
        filename_lower = filename.lower()

        ext = ""
        if "." in filename_lower:
            ext = "." + filename_lower.rsplit(".", 1)[-1]

        # 1. 特殊处理 .ts（TypeScript vs MPEG-TS 视频流）
        if ext == ".ts":
            if FileUtils._sniff_is_text(data_sample):
                return "text/typescript"
            return original_mime

        # 2. 浏览器已给出非 octet-stream 的类型 → 直接信任
        if original_mime != "application/octet-stream":
            return original_mime

        # 3. 对 application/octet-stream 执行修正
        # a. 扩展名映射
        if ext and ext in TEXT_EXTENSION_MIME_MAP:
            return TEXT_EXTENSION_MIME_MAP[ext]

        # b. 无扩展名文件名映射
        if not ext and filename_lower in _TEXT_FILENAME_MAP:
            return _TEXT_FILENAME_MAP[filename_lower]

        # c. 内容嗅探
        if FileUtils._sniff_is_text(data_sample):
            return "text/plain"

        # d. 确认二进制 → 保持 application/octet-stream
        return original_mime

    @staticmethod
    def is_allowed_mime_type(mime_type: str) -> bool:
        """
        执行文件类型白名单校验。
        """
        if mime_type in ALLOWED_MIME_TYPES:
            return True
        if mime_type.startswith("text/"):
            return True
        return False

    @staticmethod
    def is_small_text_file(size: int, mime_type: str) -> bool:
        """
        判定是否符合数据库纯文本直接存储条件。
        条件: size <= 256KB 且属于文本类型。
        """
        if size > 262144:  # 256KB
            return False

        is_text = mime_type.startswith("text/") or mime_type in _KNOWN_TEXT_APPLICATION_TYPES
        return is_text

    @staticmethod
    def decode_to_utf8(data: bytes) -> str:
        """
        强制将二进制数据转码为 UTF-8 字符串。
        """
        if not data:
            return ""

        # 1. 尝试直接 utf-8 解码
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            pass

        # 2. 尝试使用 charset-normalizer 嗅探并解码
        match = charset_normalizer.from_bytes(data).best()
        if match and match.encoding:
            try:
                return data.decode(match.encoding)
            except Exception:
                pass

        # 3. 失败拒绝保存
        raise ValueError("文件必须是有效的文本编码")

