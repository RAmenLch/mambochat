# backend/services/generation/tools/web_search_tool_provider.py

import json
import logging
import os
import re
from html import unescape
from typing import List, Optional, Dict, Any, AsyncGenerator
from urllib.parse import urlparse, parse_qs

import httpx
from langchain_core.tools import BaseTool, tool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.web_search_reader import read_webpage
from backend.schemas import enums as schemas_enums
from backend.schemas.enums import WebSearchMode
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.models.base_model import generate_uuid
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage,
    UpdateSubMessageContent,
    UpdateSubMessageStatus,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEOUT = 20

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

SAFE_SEARCH_PARAM = {"strict": "1", "moderate": "-1", "off": "-2"}


# ---------------------------------------------------------------------------
# DuckDuckGo HTML 搜索（自实现）
# ---------------------------------------------------------------------------

def _decode_uddg_url(raw_url: str) -> str:
    """解码 DuckDuckGo 重定向链接，提取真实 URL。"""
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    try:
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if uddg and uddg[0]:
            return uddg[0]
    except Exception:
        pass
    return raw_url


def _decode_html_entities(text: str) -> str:
    """解码 HTML 实体。"""
    text = unescape(text)
    text = re.sub(
        r"&#x([0-9a-fA-F]+);",
        lambda m: chr(int(m.group(1), 16)),
        text,
    )
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return text


def _is_bot_challenge(html: str) -> bool:
    """检测 DDG 是否返回了验证码页面。"""
    if 'class="result__a"' in html or "class='result__a'" in html:
        return False
    return bool(
        re.search(
            r"g-recaptcha|are you a human|id=\"challenge-form\"|name=\"challenge\"",
            html,
            re.IGNORECASE,
        )
    )


def _strip_html(text: str) -> str:
    """去除 HTML 标签，合并空白。"""
    text = HTML_TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _parse_ddg_html(html: str) -> list[dict[str, str]]:
    """从 DDG HTML 页面解析搜索结果。"""
    results: list[dict[str, str]] = []

    result_re = re.compile(
        r'<a\b(?=[^>]*\bclass="[^"]*\bresult__a\b[^"]*")([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r'<a\b(?=[^>]*\bclass="[^"]*\bresult__snippet\b[^"]*")[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in result_re.finditer(html):
        raw_attrs = match.group(1)
        raw_title = match.group(2)
        raw_url = re.search(r'href="([^"]*)"', raw_attrs, re.IGNORECASE)
        if not raw_url:
            continue
        href = raw_url.group(1)

        match_end = match.end()
        trailing = html[match_end:]
        next_result = result_re.search(trailing)
        scoped = trailing[: next_result.start()] if next_result else trailing
        snippet_match = snippet_re.search(scoped)
        raw_snippet = snippet_match.group(1) if snippet_match else ""

        title = _decode_html_entities(_strip_html(raw_title))
        url = _decode_uddg_url(_decode_html_entities(href))
        snippet = _decode_html_entities(_strip_html(raw_snippet))

        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


async def _ddg_search(query: str, max_results: int = 10, proxy_url: Optional[str] = None) -> list[dict[str, str]]:
    """原生 DDG HTML 搜索。"""
    params: dict[str, str] = {
        "q": query,
        "kp": SAFE_SEARCH_PARAM["moderate"],
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, proxy=proxy_url) as client:
        resp = await client.post(
            DDG_HTML_ENDPOINT,
            data=params,
            headers=headers,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"DDG 搜索返回 HTTP {resp.status_code}")
        html = resp.text

    if _is_bot_challenge(html):
        raise RuntimeError("DDG 返回了验证码页面，请稍后重试")

    results = _parse_ddg_html(html)
    return results[:max_results]


# ---------------------------------------------------------------------------
# WebSearchToolProvider
# ---------------------------------------------------------------------------

class WebSearchToolProvider(BaseToolProvider):
    """
    联网搜索工具提供者（内置原生工具，不依赖 MCP 进程）。

    工具集：
    - read_webpage: 抓取并提取网页正文（Markdown 格式）
    - ddgs_search: DuckDuckGo 网页搜索

    根据 web_search_mode 参数决定暴露哪些工具：
    - None: 不加载任何工具
    - DIRECT_READ: 仅 read_webpage
    - SEARCH_AND_READ: read_webpage + ddgs_search
    """

    TOOL_NAME_READ_WEBPAGE = "read_webpage"
    TOOL_NAME_DDGS_SEARCH = "ddgs_search"

    def __init__(self, web_search_mode: Optional[WebSearchMode], proxy_url: Optional[str] = None) -> None:
        if web_search_mode == WebSearchMode.DISABLE:
            web_search_mode = None
        self._web_search_mode = web_search_mode
        self._proxy_url = proxy_url

        # 状态映射
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        if self._web_search_mode is None or self._web_search_mode not in (
            WebSearchMode.DIRECT_READ,
            WebSearchMode.SEARCH_AND_READ,
        ):
            return []

        provider_self = self

        tools: List[BaseTool] = []

        # --- read_webpage（所有模式都提供）---
        @tool(provider_self.TOOL_NAME_READ_WEBPAGE)
        async def _read_webpage_tool(url: str) -> str:
            """
            获取并提取网页正文内容（Markdown 格式）。

            Args:
                url: 目标网页链接。
            """
            return await read_webpage(url, proxy_url=self._proxy_url)

        tools.append(_read_webpage_tool)

        # --- ddgs_search（仅在 SEARCH_AND_READ 模式下提供）---
        if self._web_search_mode == WebSearchMode.SEARCH_AND_READ:

            @tool(provider_self.TOOL_NAME_DDGS_SEARCH)
            async def ddgs_search(query: str, max_results: int = 10) -> str:
                """
                使用 DuckDuckGo 进行网络文本搜索。

                Args:
                    query: 搜索关键词。
                    max_results: 返回结果的最大数量，默认 10。
                """
                if not query or not query.strip():
                    return json.dumps({"error": "查询参数不能为空"}, ensure_ascii=False)

                print(f"[DDG] 搜索: {query}", file=os.sys.stderr)

                try:
                    results = await _ddg_search(query, max_results=max_results, proxy_url=self._proxy_url)
                    if not results:
                        return json.dumps(
                            {"message": f"未找到关于 '{query}' 的结果"},
                            ensure_ascii=False,
                        )
                    return json.dumps(results, ensure_ascii=False, indent=2)
                except Exception as e:
                    error_msg = f"搜索出错[{type(e).__name__}]: {e or repr(e)}"
                    print(error_msg, file=os.sys.stderr)

                    import traceback
                    traceback.print_exc(file=os.sys.stderr)

                    return json.dumps({"error": error_msg}, ensure_ascii=False)

            tools.append(ddgs_search)

        return tools

    def get_system_prompt_injection(self) -> Optional[str]:
        if self._web_search_mode is None:
            return None

        prompt_parts = [
            "## Web Search Capability",
            "You have the ability to access the internet to fetch real-time information.",
        ]

        if self._web_search_mode == WebSearchMode.DIRECT_READ:
            prompt_parts.append(
                "You can read web pages directly. When a user provides a URL, "
                "use the `read_webpage` tool to fetch and extract its content."
            )
        elif self._web_search_mode == WebSearchMode.SEARCH_AND_READ:
            prompt_parts.append(
                "You can search the web using DuckDuckGo and read web pages.\n"
                "1. Use `ddgs_search` to find relevant pages for a topic.\n"
                "2. Use `read_webpage` to fetch the full content of a specific URL.\n"
                "Always read the source page before citing or summarizing its content."
            )

        return "\n".join(prompt_parts)

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in (
            self.TOOL_NAME_READ_WEBPAGE,
            self.TOOL_NAME_DDGS_SEARCH,
        )

    async def create_call_instruction(
        self,
        tool_call_id: str,
        name: str,
        arguments: Dict[str, Any],
        tool_def: Optional[BaseTool] = None,
        run_uuid: Optional[str] = None,
    ) -> AsyncGenerator[BaseInstruction, None]:
        input_schema = tool_def.args if tool_def else None

        tool_content = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=arguments,
            input_schema=input_schema,
            run_uuid=run_uuid,
        )

        self._tool_info_cache[tool_call_id] = tool_content
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=tool_content.to_json_string(),
            config=SubMessageConfig(is_minimal=True),
        )

    async def create_result_instruction(
        self,
        tool_call_id: str,
        result_text: str,
        is_error: bool,
        media: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        if sub_id and cached_content:
            cached_content.result = result_text
            cached_content.is_error = is_error

            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string(),
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED,
            )

    def restore_state(
        self, tool_call_id: str, sub_message_id: str, tool_content: Any
    ) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
