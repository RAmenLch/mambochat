import os
import json
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量
load_dotenv()

# 配置默认用户代理
USER_AGENT = os.getenv("USER_AGENT",
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 全局变量存储搜索结果，用于通过ID引用
# 结构: {id: {"id": str, "title": str, "link": str, "snippet": str}}
SEARCH_RESULTS = {}

# 创建 MCP 服务器实例
mcp = FastMCP("bing-search", version="1.0.0")


async def _get_headers():
    return {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'Cookie': 'SRCHHPGUSR=SRCHLANG=zh-Hans; _EDGE_S=ui=zh-cn; _EDGE_V=1'
    }


@mcp.tool()
async def bing_search(query: str, num_results: int = 5) -> str:
    """
    使用必应搜索指定的关键词，并返回搜索结果列表。
    返回结果包含标题、链接、摘要和ID。ID可用于fetch_webpage工具。
    """
    global SEARCH_RESULTS
    search_url = f"https://cn.bing.com/search?q={query}&setlang=zh-CN&ensearch=0"
    print(f"正在搜索URL: {search_url}", file=sys.stderr)

    headers = await _get_headers()

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            print(f"搜索响应状态: {response.status_code}", file=sys.stderr)

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')

            results = []

            # 更新选择器列表，针对中文必应结果优化
            result_selectors = [
                '#b_results > li.b_algo',
                '#b_results > .b_ans',
                '#b_results > li'
            ]

            found_results = False

            for selector in result_selectors:
                elements = soup.select(selector)
                if not elements:
                    continue

                print(f"使用选择器 {selector} 找到了 {len(elements)} 个元素", file=sys.stderr)

                for index, element in enumerate(elements):
                    if len(results) >= num_results:
                        break

                    # 排除广告
                    if "b_ad" in element.get("class", []):
                        continue

                    # 提取标题和链接
                    title = ""
                    link = ""

                    title_elem = element.select_one('h2 a')
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        link = title_elem.get('href', '')

                    if not title:
                        alt_title_elem = element.select_one('.b_title a, a.tilk, a strong')
                        if alt_title_elem:
                            title = alt_title_elem.get_text(strip=True)
                            link = alt_title_elem.get('href', '')

                    # 提取摘要
                    snippet = ""
                    snippet_elem = element.select_one('.b_caption p, .b_snippet, .b_algoSlug')
                    if snippet_elem:
                        snippet = snippet_elem.get_text(strip=True)

                    if not snippet:
                        snippet = element.get_text(strip=True)
                        if title and title in snippet:
                            snippet = snippet.replace(title, '').strip()
                        if len(snippet) > 150:
                            snippet = snippet[:150] + '...'

                    # 修复链接
                    if link and not link.startswith('http'):
                        if link.startswith('/'):
                            link = f"https://cn.bing.com{link}"
                        else:
                            link = f"https://cn.bing.com/{link}"

                    if not title and not snippet:
                        continue

                    result_id = f"result_{int(time.time())}_{index}"

                    result_obj = {
                        "id": result_id,
                        "title": title,
                        "link": link,
                        "snippet": snippet
                    }

                    SEARCH_RESULTS[result_id] = result_obj
                    results.append(result_obj)

                if len(results) > 0:
                    found_results = True
                    break

            # 备用策略：如果没有找到结果，提取所有看起来像结果的链接
            if not found_results and len(results) == 0:
                print('使用选择器未找到结果，尝试直接提取链接', file=sys.stderr)
                links = soup.find_all('a')
                for index, a_tag in enumerate(links):
                    if len(results) >= num_results:
                        break

                    title = a_tag.get_text(strip=True)
                    link = a_tag.get('href', '')

                    if not title or not link or link == '#' or link.startswith('javascript:'):
                        continue

                    full_link = link
                    if not link.startswith('http'):
                        if link.startswith('/'):
                            full_link = f"https://cn.bing.com{link}"
                        else:
                            full_link = f"https://cn.bing.com/{link}"

                    # 简单的启发式判断
                    is_likely_result = ('bing.com/search' in full_link or
                                        query.lower() in title.lower() or
                                        query.lower() in full_link.lower())

                    if is_likely_result:
                        result_id = f"result_{int(time.time())}_link_{index}"
                        snippet = f"来自 {full_link} 的结果"

                        result_obj = {
                            "id": result_id,
                            "title": title,
                            "link": full_link,
                            "snippet": snippet
                        }
                        SEARCH_RESULTS[result_id] = result_obj
                        results.append(result_obj)

            # 最后的兜底
            if len(results) == 0:
                fallback_id = f"result_{int(time.time())}_fallback"
                fallback_result = {
                    "id": fallback_id,
                    "title": f"搜索结果: {query}",
                    "link": search_url,
                    "snippet": f"未能解析关于 '{query}' 的搜索结果，但您可以直接访问必应搜索页面查看。"
                }
                SEARCH_RESULTS[fallback_id] = fallback_result
                results.append(fallback_result)

            return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"搜索失败: {str(e)}"
        print(error_msg, file=sys.stderr)
        return json.dumps([{"error": error_msg}], ensure_ascii=False)


@mcp.tool()
async def fetch_webpage(result_id: str) -> str:
    """
    根据提供的ID获取对应网页的内容。
    result_id 必须来自于 bing_search 返回的结果。
    """
    global SEARCH_RESULTS

    result = SEARCH_RESULTS.get(result_id)
    if not result:
        return f"错误: 找不到ID为 {result_id} 的搜索结果"

    url = result['link']
    print(f"正在获取网页内容: {url}", file=sys.stderr)

    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Referer': 'https://cn.bing.com/'
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            print(f"获取网页响应状态: {response.status_code}", file=sys.stderr)

            # 自动处理编码，但如果自动失败，httpx通常做得不错
            # 也可以手动根据 Content-Type 设置 encoding
            if response.encoding is None:
                response.encoding = 'utf-8'

            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # 移除不需要的元素
            for tag in soup(['script', 'style', 'iframe', 'noscript', 'nav', 'header', 'footer', 'svg']):
                tag.decompose()

            # 尝试根据类名移除常见的干扰元素
            for selector in ['.header', '.footer', '.nav', '.sidebar', '.ad', '.advertisement', '#header', '#footer',
                             '#nav', '#sidebar']:
                for tag in soup.select(selector):
                    tag.decompose()

            # 获取主要内容
            content = ""

            # 1. 尝试语义化标签
            main_selectors = [
                'main', 'article', '.article', '.post', '.content', '#content',
                '.main', '#main', '.body', '.entry-content', '.post-content'
            ]

            for selector in main_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator='\n', strip=True)
                    if len(text) > 100:
                        content = text
                        print(f"使用选择器 '{selector}' 找到内容", file=sys.stderr)
                        break

            # 2. 如果没找到，提取所有段落
            if not content or len(content) < 100:
                print('未找到主要内容区域，尝试提取所有段落', file=sys.stderr)
                paragraphs = []
                for p in soup.find_all('p'):
                    text = p.get_text(strip=True)
                    if len(text) > 20:
                        paragraphs.append(text)
                if paragraphs:
                    content = "\n\n".join(paragraphs)

            # 3. 最后的兜底：Body 文本
            if not content or len(content) < 100:
                print('从段落中未找到足够内容，获取body内容', file=sys.stderr)
                if soup.body:
                    content = soup.body.get_text(separator='\n', strip=True)

            # 清理空白
            import re
            content = re.sub(r'\n\s*\n', '\n\n', content)

            # 添加标题
            page_title = soup.title.string if soup.title else ""
            if page_title:
                content = f"标题: {page_title.strip()}\n\n{content}"

            # 截断过长内容
            max_length = 8000
            if len(content) > max_length:
                content = content[:max_length] + "... (内容已截断)"

            print(f"最终提取内容长度: {len(content)} 字符", file=sys.stderr)
            return content

    except Exception as e:
        error_msg = f"获取网页内容失败: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg


import sys

if __name__ == "__main__":
    # FastMCP 自动处理 stdio 连接
    print("必应搜索 MCP 服务器已启动 (Python)", file=sys.stderr)
    mcp.run()
