# backend/services/generation/tools/web_search_tool_provider.py

import hashlib
import json
import logging
import os
import re
from collections import OrderedDict
from html import unescape
from typing import List, Optional, Dict, Any, AsyncGenerator
from urllib.parse import urlparse, parse_qs

import httpx
from langchain_core.tools import BaseTool, tool

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.tools.deepseek_web_api import (
    MAX_SEARCH_COUNT,
    WebSearchConfig,
    deepseek_search,
)
from backend.services.generation.tools.web_search_reader import read_webpage
from backend.schemas import enums as schemas_enums
from backend.schemas.enums import WebSearchMode
from backend.schemas.message import McpToolContent, SubMessageConfig, WebSearchDisplay, WebSearchDisplayItem
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

# ori_question 上限（DeepSeek 接口限制 1~128 个字符）
MAX_ORI_QUESTION_CHARS = 128
# 结果正文防御：单条上限 + 整体预算
CONTENT_PER_ITEM_MAX_CHARS = 4000
CONTENT_TOTAL_BUDGET_CHARS = 16000

# 前端展示用短摘要截断长度（DeepSeek snippet 通常 100~200 字符）
SNIPPET_MAX_CHARS = 300
# provider 实例内展示数据缓存的最大条目数
MAX_DISPLAY_CACHE = 16

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


def _clean_ori_question(raw: Optional[str]) -> Optional[str]:
    """规范化 ori_question：去空白/换行、长度截断到接口上限。"""
    if raw is None:
        return None
    text = WHITESPACE_RE.sub(" ", str(raw)).strip()
    if not text:
        return None
    return text[:MAX_ORI_QUESTION_CHARS]


def _normalize_deepseek_results(
    results: List[Dict[str, Any]],
    include_content: bool = False,
) -> List[Dict[str, Any]]:
    """把 DeepSeek 搜索结果归一化为工具输出结构。

    include_content 为 True 时附带正文，并做双重防御：
    单条正文截断到 CONTENT_PER_ITEM_MAX_CHARS，整体正文总量不超过 CONTENT_TOTAL_BUDGET_CHARS。
    """
    normalized: List[Dict[str, Any]] = []
    content_budget = CONTENT_TOTAL_BUDGET_CHARS

    for item in results:
        entry: Dict[str, Any] = {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "summary": item.get("summary") or item.get("snippet") or "",
            "date": item.get("date"),
            "site_name": item.get("site_name"),
            "rerank_score": item.get("rerank_score"),
        }
        if include_content:
            entry["content"] = _slice_content(item.get("content") or "", content_budget)
            content_budget = max(0, content_budget - len(entry["content"]))
        normalized.append(entry)
    return normalized


def _slice_content(content: str, budget: int) -> str:
    """按单条上限与剩余预算截断正文，截断处追加提示。"""
    text = (content or "").strip()
    if not text or budget <= 0:
        return ""

    limit = min(CONTENT_PER_ITEM_MAX_CHARS, budget)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[... 正文过长，已截断 ...]"


# ---------------------------------------------------------------------------
# 前端展示数据（不进 LLM 上下文）
# ---------------------------------------------------------------------------

def _fingerprint(text: str) -> str:
    """对工具返回给 LLM 的结果文本取指纹，用于把展示数据与结果指令关联起来。"""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _site_name_from_url(url: str) -> Optional[str]:
    """从 URL 推导站点名（DDG 结果无 site_name 时兜底）。"""
    try:
        host = (urlparse(url).hostname or "").strip()
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _shorten(text: Any, limit: int = SNIPPET_MAX_CHARS) -> str:
    """截断展示用文案（不追加省略提示，前端自行做行截断）。"""
    value = WHITESPACE_RE.sub(" ", str(text or "")).strip()
    return value[:limit]


def _build_display_items(results: List[Dict[str, Any]]) -> List[WebSearchDisplayItem]:
    """把原始搜索结果转换为前端展示条目（snippet / site_icon / authority 等）。"""
    items: List[WebSearchDisplayItem] = []
    for item in results or []:
        url = str(item.get("url") or "")
        site_name = item.get("site_name") or _site_name_from_url(url)
        score = item.get("rerank_score")
        authority = item.get("authority")
        items.append(
            WebSearchDisplayItem(
                title=_shorten(item.get("title"), 300),
                url=url,
                snippet=_shorten(item.get("snippet") or item.get("summary")),
                site_name=site_name,
                site_icon=item.get("site_icon") or None,
                date=item.get("date") or None,
                rerank_score=float(score) if isinstance(score, (int, float)) else None,
                authority=authority if isinstance(authority, int) else None,
            )
        )
    return items



# ---------------------------------------------------------------------------
# WebSearchToolProvider
# ---------------------------------------------------------------------------

class WebSearchToolProvider(BaseToolProvider):
    """
    联网搜索工具提供者（内置原生工具，不依赖 MCP 进程）。

    工具集：
    - read_webpage: 抓取并提取网页正文（Markdown 格式）
    - web_search: 网页搜索（后端由全局配置决定：DuckDuckGo / DeepSeek Search）

    根据 web_search_mode 参数决定暴露哪些工具：
    - None: 不加载任何工具
    - DIRECT_READ: 仅 read_webpage
    - SEARCH_AND_READ: read_webpage + web_search
    """

    TOOL_NAME_READ_WEBPAGE = "read_webpage"
    TOOL_NAME_SEARCH = "web_search"
    TOOL_NAME_DDGS_SEARCH = "ddgs_search"  # 历史工具名，仅用于兼容存量消息回放

    def __init__(
        self,
        web_search_mode: Optional[WebSearchMode],
        config: Optional[WebSearchConfig] = None,
    ) -> None:
        if web_search_mode == WebSearchMode.DISABLE:
            web_search_mode = None
        self._web_search_mode = web_search_mode
        self._config = config or WebSearchConfig()
        self._proxy_url = self._config.proxy_url

        # 状态映射
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}
        # 展示数据缓存：key = 结果文本指纹，value = 前端展示快照（LRU，不进入 LLM 上下文）
        self._display_cache: "OrderedDict[str, WebSearchDisplay]" = OrderedDict()

    def _cache_display(self, result_text: str, display: WebSearchDisplay) -> None:
        """把展示快照按结果文本指纹缓存，供 create_result_instruction 回填到子消息。"""
        key = _fingerprint(result_text)
        self._display_cache[key] = display
        self._display_cache.move_to_end(key)
        while len(self._display_cache) > MAX_DISPLAY_CACHE:
            self._display_cache.popitem(last=False)

    def _get_display(self, result_text: str) -> Optional[WebSearchDisplay]:
        """按结果文本指纹取回展示快照，未命中（如进程重启）返回 None。"""
        key = _fingerprint(result_text)
        display = self._display_cache.get(key)
        if display is not None:
            self._display_cache.move_to_end(key)
        return display

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
            return await read_webpage(url, proxy_url=self._proxy_url, config=self._config)

        tools.append(_read_webpage_tool)

        # --- web_search（仅在 SEARCH_AND_READ 模式下提供）---
        if self._web_search_mode == WebSearchMode.SEARCH_AND_READ:
            content_enabled = self._config.need_content

            if content_enabled:

                @tool(provider_self.TOOL_NAME_SEARCH)
                async def web_search(
                    query: str,
                    max_results: Optional[int] = None,
                    ori_question: Optional[str] = None,
                    include_content: Optional[bool] = None,
                ) -> str:
                    """
                    进行网络文本搜索，返回标题、链接与摘要。

                    Args:
                        query: 搜索关键词。支持搜索语法：site:example.com、-site:example.com、
                            排除词（-广告）、精确短语（"..."）、lang:zh,en、after:2025-01-01、before:2026。
                        max_results: 期望的结果条数，取值范围 1~50；不传则使用系统默认条数。
                        ori_question: 触发本次搜索的用户原始问题（原话，1~128 字符）。当 query 是你从
                            用户问题中提炼、改写或翻译的关键词时填写，可显著提升检索相关性；
                            若 query 本身就是用户原话，请省略该参数。
                        include_content: 是否在每条结果中包含网页正文。仅在需要直接引用原文细节时传
                            true；只想先看标题与摘要时传 false 或省略。正文过长会被截断。
                    """
                    return await provider_self._run_search_tool(
                        query, max_results, ori_question, include_content
                    )

            else:

                @tool(provider_self.TOOL_NAME_SEARCH)
                async def web_search(
                    query: str,
                    max_results: Optional[int] = None,
                    ori_question: Optional[str] = None,
                ) -> str:
                    """
                    进行网络文本搜索，返回标题、链接与摘要。

                    Args:
                        query: 搜索关键词。支持搜索语法：site:example.com、-site:example.com、
                            排除词（-广告）、精确短语（"..."）、lang:zh,en、after:2025-01-01、before:2026。
                        max_results: 期望的结果条数，取值范围 1~50；不传则使用系统默认条数。
                        ori_question: 触发本次搜索的用户原始问题（原话，1~128 字符）。当 query 是你从
                            用户问题中提炼、改写或翻译的关键词时填写，可显著提升检索相关性；
                            若 query 本身就是用户原话，请省略该参数。
                    """
                    return await provider_self._run_search_tool(
                        query, max_results, ori_question, None
                    )

            tools.append(web_search)

        return tools

    async def _run_search_tool(
        self,
        query: str,
        max_results: Optional[int],
        ori_question: Optional[str],
        include_content: Optional[bool],
    ) -> str:
        """校验入参并按当前搜索后端执行检索。"""
        if not query or not str(query).strip():
            return json.dumps({"error": "查询参数不能为空"}, ensure_ascii=False)

        if self._config.error:
            return json.dumps({"error": self._config.error}, ensure_ascii=False)

        if max_results is None:
            count = self._config.result_count
        else:
            try:
                requested = int(max_results)
            except (TypeError, ValueError):
                requested = 0
            if not 1 <= requested <= MAX_SEARCH_COUNT:
                return json.dumps(
                    {
                        "error": f"max_results 必须为 1~{MAX_SEARCH_COUNT} 之间的整数；"
                                 "不传该参数则使用系统默认条数"
                    },
                    ensure_ascii=False,
                )
            count = requested

        want_content = self._config.need_content and include_content is not False

        if self._config.uses_deepseek_search:
            return await self._deepseek_search_tool(query, count, ori_question, want_content)

        return await self._ddg_search_tool(query, count)

    async def _deepseek_search_tool(
        self,
        query: str,
        count: int,
        ori_question: Optional[str] = None,
        include_content: bool = False,
    ) -> str:
        """调用 DeepSeek Search 接口并返回工具结果文本。"""
        clean_ori_question = _clean_ori_question(ori_question)
        print(
            f"[DeepSeek|search] 搜索: {query} (count={count}, content={include_content}"
            f"{', ori_question=' + clean_ori_question if clean_ori_question else ''})",
            file=os.sys.stderr,
        )

        try:
            results = await deepseek_search(
                query,
                api_base=self._config.api_base,
                api_key=self._config.api_key,
                count=count,
                need_content=include_content,
                proxy_url=self._proxy_url,
                ori_question=clean_ori_question,
            )
        except Exception as e:
            error_msg = f"搜索出错[{type(e).__name__}]: {e or repr(e)}"
            print(error_msg, file=os.sys.stderr)
            return json.dumps({"error": error_msg}, ensure_ascii=False)

        if not results:
            return json.dumps({"message": f"未找到关于 '{query}' 的结果"}, ensure_ascii=False)

        normalized = _normalize_deepseek_results(results, include_content=include_content)
        result_text = json.dumps(normalized, ensure_ascii=False, indent=2)
        self._cache_display(
            result_text,
            WebSearchDisplay(
                provider="deepseek",
                query=query,
                count=len(normalized),
                items=_build_display_items(results),
            ),
        )
        return result_text

    async def _ddg_search_tool(self, query: str, count: int) -> str:
        """调用内置 DuckDuckGo 搜索并返回工具结果文本。"""
        print(f"[DDG] 搜索: {query}", file=os.sys.stderr)

        try:
            results = await _ddg_search(query, max_results=count, proxy_url=self._proxy_url)
            if not results:
                return json.dumps(
                    {"message": f"未找到关于 '{query}' 的结果"},
                    ensure_ascii=False,
                )
            result_text = json.dumps(results, ensure_ascii=False, indent=2)
            self._cache_display(
                result_text,
                WebSearchDisplay(
                    provider="duckduckgo",
                    query=query,
                    count=len(results),
                    items=_build_display_items(results),
                ),
            )
            return result_text
        except Exception as e:
            error_msg = f"搜索出错[{type(e).__name__}]: {e or repr(e)}"
            print(error_msg, file=os.sys.stderr)

            import traceback
            traceback.print_exc(file=os.sys.stderr)

            return json.dumps({"error": error_msg}, ensure_ascii=False)

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
            engine = "DeepSeek Search" if self._config.uses_deepseek_search else "DuckDuckGo"
            prompt_lines = [
                f"You can search the web using {engine} and read web pages.",
                "1. Use `web_search` to find relevant pages for a topic.",
                "2. Use `read_webpage` to fetch the full content of a specific URL.",
            ]
            if self._config.uses_deepseek_search:
                prompt_lines.append(
                    "3. `web_search.query` should be short keywords, not a full sentence. When you rewrite, "
                    "condense or translate the user's wording, also pass `ori_question` with the user's "
                    "original question (<=128 chars) so the engine understands the real intent; omit it "
                    "when `query` already is the user's original wording."
                )
                prompt_lines.append(
                    "4. Search operators are supported inside `query`: site:example.com, -site:example.com, "
                    "-word, \"exact phrase\", lang:zh,en, after:2025-01-01, before:2026."
                )
                if self._config.need_content:
                    prompt_lines.append(
                        "5. Pass `include_content=true` only when you need verbatim page text (long content "
                        "is truncated); leave it out for a lightweight overview of titles and summaries."
                    )
            prompt_lines.append("Always read the source page before citing or summarizing its content.")
            prompt_parts.append("\n".join(prompt_lines))

        return "\n".join(prompt_parts)

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name in (
            self.TOOL_NAME_READ_WEBPAGE,
            self.TOOL_NAME_SEARCH,
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

            # 搜索结果展示快照（snippet / site_icon / authority 等）按结果文本指纹回填，
            # 仅用于前端渲染，不参与 to_openai_tool_result_message，永不进入 LLM 上下文。
            if not is_error and cached_content.display is None:
                display = self._get_display(result_text)
                if display is not None:
                    cached_content.display = display

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
