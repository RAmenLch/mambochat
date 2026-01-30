import os
import json
import httpx
from typing import Optional
from mcp.server.fastmcp import FastMCP

# 初始化 MCP 服务器
mcp = FastMCP("knowledge-base-tools")

# 从环境变量获取配置
# 默认后端地址，可根据部署情况通过环境变量覆盖
API_BASE_URL = os.getenv("MAMBOCHAT_API_BASE_URL", "http://127.0.0.1:8000")
# 必须通过环境变量注入的目标资源ID (Knowledge Base ID)
TARGET_RESOURCE_ID = os.getenv("MAMBOCHAT_RESOURCE_ID")


def _get_client() -> httpx.AsyncClient:
    """获取配置好的 HTTP 客户端"""
    return httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0)


@mcp.tool()
async def search_knowledge_base(query: str, top_k: int = 10) -> str:
    """
    在当前挂载的知识库中进行语义搜索。

    Args:
        query (str): 搜索关键词或自然语言问题。
        top_k (int): 返回的最相似结果数量，默认为 10。

    Returns:
        str: JSON 格式的搜索结果列表，包含切片内容、来源文件及相似度分数。
    """
    if not TARGET_RESOURCE_ID:
        return json.dumps({
            "error": "Configuration Error: MAMBOCHAT_RESOURCE_ID environment variable is not set."
        }, ensure_ascii=False)

    if not query or not query.strip():
        return json.dumps({"error": "Query parameter cannot be empty."}, ensure_ascii=False)

    payload = {
        "query_text": query,
        "kb_id": TARGET_RESOURCE_ID,
        "top_k": top_k
    }

    try:
        async with _get_client() as client:
            response = await client.post("/api/resources/kb/search", json=payload)
            
            if response.status_code != 200:
                return json.dumps({
                    "error": f"API Error ({response.status_code}): {response.text}"
                }, ensure_ascii=False)
            
            data = response.json()
            # 返回 items 列表
            return json.dumps(data.get("items", []), ensure_ascii=False, indent=2)

    except httpx.RequestError as e:
        return json.dumps({
            "error": f"Network Error: {str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected Error: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
async def get_resource_chunks(
    min_index: Optional[int] = None,
    max_index: Optional[int] = None,
    page: int = 1,
    page_size: int = 20
) -> str:
    """
    读取当前挂载资源（知识库文件）的切片列表。
    支持按索引范围筛选和分页读取。
    在search_knowledge_base的结果不足以解决问题时,可以用于基于search_knowledge_base返回的chunk_index,对临近chunk进行筛查
    Args:
        min_index (int, optional): 切片索引最小值（包含）。
        max_index (int, optional): 切片索引最大值（包含）。
        page (int): 页码，默认为 1。
        page_size (int): 每页数量，默认为 20。

    Returns:
        str: JSON 格式的切片列表及总数。
    """
    if not TARGET_RESOURCE_ID:
        return json.dumps({
            "error": "Configuration Error: MAMBOCHAT_RESOURCE_ID environment variable is not set."
        }, ensure_ascii=False)

    params = {
        "page": page,
        "page_size": page_size
    }
    if min_index is not None:
        params["min_index"] = min_index
    if max_index is not None:
        params["max_index"] = max_index

    try:
        async with _get_client() as client:
            # 构建路径：/api/resources/kb/{resource_id}/chunks
            url = f"/api/resources/kb/{TARGET_RESOURCE_ID}/chunks"
            response = await client.get(url, params=params)

            if response.status_code != 200:
                return json.dumps({
                    "error": f"API Error ({response.status_code}): {response.text}"
                }, ensure_ascii=False)

            data = response.json()
            return json.dumps(data, ensure_ascii=False, indent=2)

    except httpx.RequestError as e:
        return json.dumps({
            "error": f"Network Error: {str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected Error: {str(e)}"
        }, ensure_ascii=False)


if __name__ == "__main__":
    # 启动 MCP 服务器，使用 stdio 传输
    mcp.run(transport="stdio")
