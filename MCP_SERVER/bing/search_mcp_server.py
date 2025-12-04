import os
import sys
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
mcp = FastMCP("bing-search")


async def _get_headers():
    """生成伪装的请求头"""
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
    执行必应(Bing)网络搜索。

    当用户需要查询实时信息、新闻、技术文档或任何训练数据之外的知识时使用此工具。

    Args:
        query (str): 搜索关键词。支持自然语言描述，例如 "Python httpx 教程" 或 "今天北京天气"。
                     系统会自动处理URL编码，无需手动转义空格或特殊字符。
        num_results (int): 需要返回的搜索结果数量，默认为 5。建议不超过 10。

    Returns:
        str: 一个 JSON 格式的字符串列表。每个对象包含:
             - id: 结果的唯一标识符 (用于后续调用 fetch_webpage)
             - title: 网页标题
             - link: 网页链接
             - snippet: 网页摘要
    """
    global SEARCH_RESULTS

    # 1. 入参校验
    if not query or not query.strip():
        return json.dumps([{"error": "查询参数 query 不能为空"}], ensure_ascii=False)

    query = query.strip()
    base_url = "https://cn.bing.com/search"

    # 2. 使用 params 字典，httpx 会自动处理 URL 编码 (空格 -> +, 中文 -> %XX)
    params = {
        "q": query,
        "setlang": "zh-CN",
        "ensearch": "0"
    }

    print(f"正在搜索: {query}", file=sys.stderr)

    headers = await _get_headers()

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # 传递 params 而不是手动拼接 URL
            response = await client.get(base_url, params=params, headers=headers)
            print(f"搜索响应状态: {response.status_code} | URL: {response.url}", file=sys.stderr)

            if response.status_code != 200:
                return json.dumps([{"error": f"搜索引擎返回非200状态码: {response.status_code}"}], ensure_ascii=False)

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')

            results = []

            # 针对中文必应结果优化的选择器
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

                    # 修复相对链接
                    if link and not link.startswith('http'):
                        if link.startswith('/'):
                            link = f"https://cn.bing.com{link}"
                        else:
                            link = f"https://cn.bing.com/{link}"

                    if not title and not snippet:
                        continue

                    # 生成唯一ID
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

            # 兜底策略：如果没找到标准结果，尝试提取所有链接
            if not found_results and len(results) == 0:
                print('常规解析未找到结果，尝试兜底策略', file=sys.stderr)
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
                        full_link = f"https://cn.bing.com{link}" if link.startswith('/') else f"https://cn.bing.com/{link}"

                    # 简单的启发式判断：链接或标题包含查询词
                    is_likely_result = (query.lower() in title.lower())

                    if is_likely_result:
                        result_id = f"result_{int(time.time())}_link_{index}"
                        result_obj = {
                            "id": result_id,
                            "title": title,
                            "link": full_link,
                            "snippet": f"包含关键词的链接: {title}"
                        }
                        SEARCH_RESULTS[result_id] = result_obj
                        results.append(result_obj)

            if len(results) == 0:
                return json.dumps([{"message": f"未找到关于 '{query}' 的结果", "link": str(response.url)}], ensure_ascii=False)

            return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"搜索工具执行出错: {str(e)}"
        print(error_msg, file=sys.stderr)
        return json.dumps([{"error": error_msg}], ensure_ascii=False)


@mcp.tool()
async def fetch_webpage(result_id: str) -> str:
    """
    深入阅读指定网页的详细内容。

    通常在调用 `bing_search` 后，如果摘要信息不足以回答问题，使用此工具获取全文。

    Args:
        result_id (str): 必须是 `bing_search` 返回结果中的 `id` 字段 (例如 "result_171000_0")。
                         **不要**直接传入 URL 链接。

    Returns:
        str: 网页的纯文本内容。已去除广告、导航栏等无关信息。
             如果 ID 无效或抓取失败，将返回错误描述。
    """
    global SEARCH_RESULTS

    if not result_id:
        return "错误: result_id 不能为空"

    result = SEARCH_RESULTS.get(result_id)
    if not result:
        return f"错误: 找不到ID为 '{result_id}' 的搜索结果。请确保先调用 bing_search 并使用返回的 id。"

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

            if response.status_code >= 400:
                return f"获取网页失败，HTTP状态码: {response.status_code}"

            # 自动处理编码
            if response.encoding is None:
                response.encoding = 'utf-8'

            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # 移除不需要的元素 (增强版)
            for tag in soup(['script', 'style', 'iframe', 'noscript', 'nav', 'header', 'footer', 'svg', 'button', 'form']):
                tag.decompose()

            # 移除常见的干扰类名
            ignore_classes = [
                '.header', '.footer', '.nav', '.sidebar', '.ad', '.advertisement',
                '.cookie-banner', '.popup', '.menu', '.social-share'
            ]
            for selector in ignore_classes:
                for tag in soup.select(selector):
                    tag.decompose()

            # 获取主要内容
            content = ""

            # 1. 优先尝试语义化标签
            main_selectors = [
                'main', 'article', '.article', '.post-content', '.entry-content',
                '#content', '.content', '.main-content'
            ]

            for selector in main_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator='\n', strip=True)
                    if len(text) > 100:
                        content = text
                        print(f"使用选择器 '{selector}' 提取成功", file=sys.stderr)
                        break

            # 2. 备选：提取所有段落
            if not content or len(content) < 100:
                paragraphs = []
                for p in soup.find_all('p'):
                    text = p.get_text(strip=True)
                    if len(text) > 20: # 过滤太短的段落
                        paragraphs.append(text)
                if paragraphs:
                    content = "\n\n".join(paragraphs)

            # 3. 最后的兜底
            if not content or len(content) < 100:
                if soup.body:
                    content = soup.body.get_text(separator='\n', strip=True)

            # 文本清洗
            import re
            # 将连续的换行符替换为两个换行符
            content = re.sub(r'\n\s*\n', '\n\n', content)
            # 移除过多的空白字符
            content = re.sub(r'[ \t]+', ' ', content)

            # 添加标题上下文
            page_title = soup.title.string if soup.title else result.get('title', '无标题')
            final_output = f"来源: {url}\n网页标题: {page_title.strip()}\n{'='*20}\n\n{content}"

            # 截断过长内容 (防止超出 LLM 上下文限制)
            max_length = 12000
            if len(final_output) > max_length:
                final_output = final_output[:max_length] + "\n\n[...内容过长已截断...]"

            print(f"提取内容长度: {len(final_output)} 字符", file=sys.stderr)
            return final_output

    except Exception as e:
        error_msg = f"获取网页内容时发生异常: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg


if __name__ == "__main__":
    print("必应搜索 MCP 服务器已启动 (Python)", file=sys.stderr)
    mcp.run()
