# backend/services/generation/tools/deepseek_web_api.py
"""DeepSeek 网页搜索 / 抓取接口客户端。

接口文档: https://api-docs.deepseek.com/zh-cn/guides/search
- Search: POST {base}/v1/tools/search，返回结构化搜索结果
- Fetch : POST {base}/v1/tools/fetch，返回网页 Markdown 正文

两者均为只读接口，使用与 DeepSeek API 相同的 Bearer 鉴权。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

DEFAULT_DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_SEARCH_PATH = "/v1/tools/search"
DEEPSEEK_FETCH_PATH = "/v1/tools/fetch"
DEFAULT_TIMEOUT = 30
MAX_SEARCH_COUNT = 50
MIN_SEARCH_COUNT = 1


@dataclass
class WebSearchConfig:
    """网页搜索运行期配置（由全局配置解析而来）。"""

    provider: str = "duckduckgo"          # duckduckgo | deepseek
    api_base: Optional[str] = None        # DeepSeek 服务地址（已归一化）
    api_key: Optional[str] = None
    result_count: int = 10                # 1~50
    need_content: bool = False            # Search 是否直接返回正文
    reader: str = "deepseek"              # deepseek（Fetch 接口）| local（本地解析）
    proxy_url: Optional[str] = None
    error: Optional[str] = None           # 配置解析失败原因（工具调用时直接返回）

    @property
    def uses_deepseek_search(self) -> bool:
        return self.provider == "deepseek"

    @property
    def uses_deepseek_fetch(self) -> bool:
        """网页读取是否走 DeepSeek Fetch（需 DeepSeek 后端 + reader=deepseek）。"""
        if self.reader == "local":
            return False
        return self.uses_deepseek_search

    @property
    def ready(self) -> bool:
        if self.error:
            return False
        if self.uses_deepseek_search or self.uses_deepseek_fetch:
            return bool(self.api_base and self.api_key)
        return True


def normalize_deepseek_base(api_host: Optional[str]) -> str:
    """把服务商 apiHost 归一化为 DeepSeek 根地址（不含 /v1 等路径后缀）。"""
    base = (api_host or "").strip()
    if not base:
        return DEFAULT_DEEPSEEK_BASE

    if not base.lower().startswith(("http://", "https://")):
        base = f"https://{base}"

    parsed = urlparse(base)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base.rstrip("/")
    return base or DEFAULT_DEEPSEEK_BASE


def is_deepseek_host(api_host: Optional[str]) -> bool:
    """判断服务商 apiHost 是否指向 DeepSeek 官方域名（以域名判断，与 worker_type 无关）。"""
    raw = (api_host or "").strip()
    if not raw:
        return False
    if not raw.lower().startswith(("http://", "https://")):
        raw = f"https://{raw}"

    try:
        hostname = (urlparse(raw).hostname or "").lower()
    except ValueError:
        return False
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


def _error_message(status_code: int, payload: Any) -> str:
    detail = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        elif error:
            detail = str(error)

    hints = {
        400: "请求参数不合法",
        401: "DeepSeek API Key 缺失或无效",
        402: "DeepSeek 账号余额不足",
        403: "Fetch 请求被安全策略拒绝",
        404: "DeepSeek 未能获取可用网页内容",
        408: "DeepSeek 读取请求体超时",
        413: "请求体超过大小限制",
        429: "超过 DeepSeek Search/Fetch 的 QPS 限制（5 次/秒）",
        500: "DeepSeek 服务器内部错误",
        504: "DeepSeek 下游请求超时",
    }
    hint = hints.get(status_code, "DeepSeek 接口调用失败")
    return f"{hint}（HTTP {status_code}）" + (f": {detail}" if detail else "")


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def deepseek_search(
    query: str,
    api_base: str,
    api_key: str,
    count: int = 10,
    need_content: bool = False,
    proxy_url: Optional[str] = None,
    ori_question: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """调用 DeepSeek Search 接口，返回原始 results 列表。"""
    payload: Dict[str, Any] = {
        "query": query,
        "count": max(MIN_SEARCH_COUNT, min(MAX_SEARCH_COUNT, int(count))),
        "need_content": bool(need_content),
    }

    if ori_question:
        payload["ori_question"] = ori_question

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, proxy=proxy_url) as client:
        resp = await client.post(
            f"{normalize_deepseek_base(api_base)}{DEEPSEEK_SEARCH_PATH}",
            json=payload,
            headers=_headers(api_key),
        )

    try:
        data = resp.json()
    except Exception:
        data = None

    if resp.status_code != 200:
        raise RuntimeError(_error_message(resp.status_code, data))

    if not isinstance(data, dict):
        raise RuntimeError("DeepSeek Search 返回了无法解析的响应")
    return data.get("results") or []


async def deepseek_fetch(
    url: str,
    api_base: str,
    api_key: str,
    proxy_url: Optional[str] = None,
) -> Dict[str, str]:
    """调用 DeepSeek Fetch 接口，返回 {title, content}。"""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, proxy=proxy_url) as client:
        resp = await client.post(
            f"{normalize_deepseek_base(api_base)}{DEEPSEEK_FETCH_PATH}",
            json={"url": url},
            headers=_headers(api_key),
        )

    try:
        data = resp.json()
    except Exception:
        data = None

    if resp.status_code != 200:
        raise RuntimeError(_error_message(resp.status_code, data))

    if not isinstance(data, dict):
        raise RuntimeError("DeepSeek Fetch 返回了无法解析的响应")
    return {
        "title": data.get("title") or "",
        "content": data.get("content") or "",
    }
