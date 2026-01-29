import os
import asyncio
import json
from typing import Optional

from ddgs import DDGS
from mcp.server.fastmcp import FastMCP
import trafilatura

# 创建 MCP 服务器实例
mcp = FastMCP("ddgs-search-tools")

@mcp.tool()
async def ddgs_search(query: str, max_results: int = 10) -> str:
    """
    使用 DDGS (Dux Distributed Global Search) 进行网络文本搜索。

    Args:
        query (str): 搜索关键词。
        max_results (int): 返回结果的最大数量，默认为 10。

    Returns:
        str: JSON 格式的搜索结果列表，包含 title, href, body。
    """
    if not query or not query.strip():
        return json.dumps({"error": "查询参数不能为空"}, ensure_ascii=False)

    print(f"🔍 正在使用 DDGS 搜索: {query}", file=os.sys.stderr)

    try:
        # DDGS 库是同步的，使用 asyncio.to_thread 避免阻塞事件循环
        def _sync_search():
            # 使用 with 语句确保资源正确释放
            with DDGS() as ddgs:
                # 调用 text 方法进行搜索
                results = ddgs.text(
                    query,
                    region="us-en",
                    safesearch="moderate",
                    max_results=max_results,
                    backend="auto"
                )
                return results

        results = await asyncio.to_thread(_sync_search)

        if not results:
            return json.dumps({"message": f"未找到关于 '{query}' 的结果"}, ensure_ascii=False)

        # 返回格式化的 JSON 字符串
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"DDGS 搜索出错: {str(e)}"
        print(error_msg, file=os.sys.stderr)
        return json.dumps({"error": error_msg}, ensure_ascii=False)


# @mcp.tool()
async def read_webpage(url: str) -> str:
    """
    直接通过 URL 获取并提取网页的正文文本内容。

    Args:
        url (str): 目标网页的链接。

    Returns:
        str: 提取的网页文本内容（标题 + 正文）。
    """
    if not url:
        return "错误: URL 参数不能为空"

    print(f"📖 正在读取网页: {url}", file=os.sys.stderr)

    try:
        # 使用 trafilatura 在线程中下载和提取内容
        def _sync_fetch():
            downloaded = trafilatura.fetch_url(url)
            if downloaded is None:
                return None
            # 提取主要内容，不包含评论、表格等干扰信息
            return trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=True
            )

        content = await asyncio.to_thread(_sync_fetch)

        if not content:
            return f"无法从 {url} 提取有效内容，可能是该网站禁止访问或内容为空。"

        # 简单的长度限制，防止 Token 溢出
        if len(content) > 15000:
            content = content[:15000] + "\n\n[... 内容过长，已截断 ...]"

        return content

    except Exception as e:
        error_msg = f"读取网页时发生异常: {str(e)}"
        print(error_msg, file=os.sys.stderr)
        return error_msg

if __name__ == "__main__":
    # 启动 MCP 服务器，使用 stdio 传输
    mcp.run(transport="stdio")
