import os
import sys
import json
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import trafilatura

# 加载环境变量
load_dotenv()

# 配置默认用户代理 (用于 Bing 搜索部分)
USER_AGENT = os.getenv("USER_AGENT",
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 全局变量存储搜索结果
SEARCH_RESULTS = {}

# 创建 MCP 服务器实例
mcp = FastMCP("bing-search-optimized")

async def _get_headers():
    """生成伪装的请求头 (仅用于 Bing 搜索)"""
    return {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Site': 'none',
        'Cookie': 'SRCHHPGUSR=SRCHLANG=zh-Hans; _EDGE_S=ui=zh-cn;'
    }

@mcp.tool()
async def bing_search(query: str, num_results: int = 5) -> str:
    """
    执行必应(Bing)网络搜索。

    Args:
        query (str): 搜索关键词。
        num_results (int): 返回结果数量，默认 5。
    """
    global SEARCH_RESULTS

    if not query or not query.strip():
        return json.dumps([{"error": "查询参数不能为空"}], ensure_ascii=False)

    query = query.strip()
    base_url = "https://cn.bing.com/search"
    params = {"q": query, "setlang": "zh-CN", "ensearch": "0"}

    print(f"🔍 正在搜索: {query}", file=sys.stderr)
    headers = await _get_headers()

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(base_url, params=params, headers=headers)

            if response.status_code != 200:
                return json.dumps([{"error": f"搜索失败: {response.status_code}"}], ensure_ascii=False)

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # 优化的选择器逻辑
            elements = soup.select('#b_results > li.b_algo')

            for index, element in enumerate(elements):
                if len(results) >= num_results:
                    break

                # 提取标题和链接
                title_elem = element.select_one('h2 a')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')

                # 提取摘要
                snippet_elem = element.select_one('.b_caption p, .b_snippet')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                if not link.startswith('http'):
                    continue

                # 生成唯一ID
                result_id = f"res_{int(time.time())}_{index}"

                result_obj = {
                    "id": result_id,
                    "title": title,
                    "link": link,
                    "snippet": snippet[:200] # 限制摘要长度
                }

                SEARCH_RESULTS[result_id] = result_obj
                results.append(result_obj)

            if not results:
                return json.dumps([{"message": f"未找到结果: {query}"}], ensure_ascii=False)

            return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps([{"error": str(e)}], ensure_ascii=False)


@mcp.tool()
async def fetch_webpage(result_id: str) -> str:
    """
    使用 Trafilatura 智能提取网页正文内容。

    Args:
        result_id (str): bing_search 返回的 id (如 "res_171xxx_0")。
    """
    global SEARCH_RESULTS

    if result_id not in SEARCH_RESULTS:
        return f"错误: ID '{result_id}' 无效或已过期，请重新搜索。"

    url = SEARCH_RESULTS[result_id]['link']
    print(f"📖 正在通过 Trafilatura 读取: {url}", file=sys.stderr)

    try:
        # 1. 下载网页 (在线程池中运行以避免阻塞异步循环)
        # trafilatura.fetch_url 自动处理 Header 和重试
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)

        if downloaded is None:
            return f"错误: 无法下载网页内容 ({url})"

        # 2. 提取内容 (核心优化部分)
        # include_comments=False: 不提取评论
        # include_tables=True: 保留表格数据
        # with_metadata=True: 提取标题、日期等
        result = await asyncio.to_thread(
            trafilatura.extract,
            downloaded,
            include_comments=False,
            include_tables=True,
            with_metadata=True,
            include_links=False,
            output_format="json" # 先转JSON以获取元数据，再组合文本
        )

        if not result:
            return "警告: 网页已下载，但 Trafilatura 无法提取有效正文（可能是纯图片或JS渲染页面）。"

        data = json.loads(result)

        # 3. 格式化输出给 LLM
        output_parts = [
            f"标题: {data.get('title', '未知')}",
            f"来源: {data.get('source') or url}",
            f"发布日期: {data.get('date', '未知')}",
            f"作者: {data.get('author', '未知')}",
            "=" * 30,
            data.get('text', '')
        ]

        final_text = "\n".join(output_parts)

        # 简单的长度截断，防止爆 Token
        if len(final_text) > 15000:
            final_text = final_text[:15000] + "\n\n[...内容过长，已截断...]"

        return final_text

    except Exception as e:
        error_msg = f"Trafilatura 提取异常: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg

if __name__ == "__main__":
    mcp.run()
