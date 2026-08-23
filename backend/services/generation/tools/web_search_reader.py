# backend/services/generation/tools/web_search_reader.py
"""
网页读取策略 + 路由。

内置两种读取器：
- TrafilaturaReader: 面向新闻/文章正文提取（快速，但会丢弃文档站代码块）
- Html2TextReader: 面向技术文档（保留代码块、链接、表格）

路由策略（当前写死为 html2text）：
- "trafilatura" -> TrafilaturaReader
- "html2text"   -> Html2TextReader
"""

import asyncio
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

import html2text
import httpx
from bs4 import BeautifulSoup
import trafilatura

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20
MAX_HTML_BYTES = 8_000_000
MAX_OUTPUT_CHARS = 15_000

INVISIBLE_UNICODE_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"\u200b-\u200f\u2028-\u202f\ufeff\ufff9-\ufffb]"
)
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

# 当前路由策略（后续可改为配置驱动）
_CURRENT_ROUTE: str = "html2text"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    """后处理：去除不可见字符 + 规范化空白。"""
    text = INVISIBLE_UNICODE_RE.sub("", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """截断过长文本。"""
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[... 内容过长，已截断 ...]"
    return text


# ---------------------------------------------------------------------------
# 读取器接口
# ---------------------------------------------------------------------------


class BaseWebReader(ABC):
    """网页读取器抽象基类。"""

    name: str = "base"

    @abstractmethod
    async def read(self, url: str, proxy_url: Optional[str] = None) -> str:
        """读取并提取网页内容，返回 Markdown 文本。"""
        ...


# ---------------------------------------------------------------------------
# Trafilatura 读取器
# ---------------------------------------------------------------------------


class TrafilaturaReader(BaseWebReader):
    """面向新闻/文章正文提取，速度快但会丢弃 UI 嵌套区（如文档站代码块）。"""

    name = "trafilatura"

    async def read(self, url: str, proxy_url: Optional[str] = None) -> str:
        if not url:
            return "错误: URL 参数不能为空"

        print(f"[WEB|trafilatura] 读取: {url}", file=os.sys.stderr)

        try:
            # trafilatura.fetch_url 不支持代理，改为 httpx 拉取后交给 extract
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=True,
                proxy=proxy_url,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return f"HTTP {resp.status_code}: 无法访问 {url}"
                downloaded = resp.text

            if len(downloaded) > MAX_HTML_BYTES:
                size_mb = MAX_HTML_BYTES / (1024 * 1024)
                return f"网页内容过大（超过 {size_mb:.0f}MB），无法读取"

            def _sync_extract() -> Optional[str]:
                return trafilatura.extract(
                    downloaded,
                    output_format="markdown",
                    include_comments=False,
                    include_tables=True,
                    include_links=True,
                    include_formatting=True,
                )

            content = await asyncio.to_thread(_sync_extract)

            if not content:
                return f"无法从 {url} 提取有效内容"

            return _truncate(_clean_text(content))

        except Exception as e:
            msg = f"读取网页异常 [{self.name}]: {e}"
            print(msg, file=os.sys.stderr)
            return msg


# ---------------------------------------------------------------------------
# Html2Text 读取器
# ---------------------------------------------------------------------------


class Html2TextReader(BaseWebReader):
    """面向技术文档，使用 bs4 + html2text 保留代码块、链接、表格。"""

    name = "html2text"

    def __init__(self) -> None:
        self._converter = html2text.HTML2Text()
        self._converter.body_width = 0  # 不自动换行
        self._converter.ignore_links = False
        self._converter.ignore_images = True
        self._converter.ignore_tables = False
        self._converter.protect_links = True
        self._converter.mark_code = True

    async def read(self, url: str, proxy_url: Optional[str] = None) -> str:
        if not url:
            return "错误: URL 参数不能为空"

        print(f"[WEB|html2text] 读取: {url}", file=os.sys.stderr)

        try:
            # 1. 拉取 HTML
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            }
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=True,
                proxy=proxy_url,
            ) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return f"HTTP {resp.status_code}: 无法访问 {url}"
                raw_html = resp.text

            if len(raw_html) > MAX_HTML_BYTES:
                size_mb = MAX_HTML_BYTES / (1024 * 1024)
                return f"网页内容过大（超过 {size_mb:.0f}MB），无法读取"

            # 2. 提取主体内容
            body_html = await asyncio.to_thread(self._extract_body, raw_html)

            # 3. 转为 Markdown
            markdown = await asyncio.to_thread(self._converter.handle, body_html)

            if not markdown or not markdown.strip():
                return f"无法从 {url} 提取有效内容"

            return _truncate(_clean_text(markdown))

        except Exception as e:
            msg = f"读取网页异常 [{self.name}]: {e}"
            print(msg, file=os.sys.stderr)
            return msg

    @staticmethod
    def _extract_body(html: str) -> str:
        """提取 HTML 主体区域，去除导航、侧边栏等噪音。"""
        soup = BeautifulSoup(html, "lxml")

        # 优先用 <main> / <article>
        main = soup.find("main") or soup.find("article")
        if main is not None:
            return str(main)

        # 否则用 <body> 但删除明显的非内容区
        body = soup.find("body")
        if body is None:
            return html

        # 移除导航/页脚/侧边栏/脚本/样式
        for tag_name in ("nav", "footer", "header", "aside", "script", "style", "noscript", "iframe"):
            for tag in body.find_all(tag_name):
                tag.decompose()

        return str(body)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


# 读取器实例（单例）
_TRAFILATURA = TrafilaturaReader()
_HTML2TEXT = Html2TextReader()


def set_reader_strategy(strategy: str) -> None:
    """切换读取策略。

    Args:
        strategy: "trafilatura" | "html2text"
    """
    global _CURRENT_ROUTE
    if strategy not in ("trafilatura", "html2text"):
        raise ValueError(f"不支持的读取策略: {strategy}，可选: trafilatura, html2text")
    _CURRENT_ROUTE = strategy


def get_reader() -> BaseWebReader:
    """根据当前路由返回读取器实例。"""
    if _CURRENT_ROUTE == "trafilatura":
        return _TRAFILATURA
    return _HTML2TEXT


async def read_webpage(url: str, proxy_url: Optional[str] = None) -> str:
    """读取网页内容（通过当前路由策略）。"""
    reader = get_reader()
    return await reader.read(url, proxy_url=proxy_url)
