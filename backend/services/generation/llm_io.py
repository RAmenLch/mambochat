# backend/services/generation/llm_io.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union


class LLMInput(BaseModel):
    """
    一个标准化的、与具体模型无关的LLM请求对象。
    由 Manager 创建，由 Worker 消费。
    """
    model_id: str
    messages: List[Dict[str, Any]]
    parameters: Dict[str, Any] = {}

    # 连接相关的配置
    api_host: str
    api_key: str
    proxy_url: Optional[str] = None
    timeout: int = 300
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict]] = None

class WorkerOutput(BaseModel):
    """
    一个标准化的、与具体模型无关的LLM响应块。
    由 Worker 创建，由 Manager 消费。
    """
    type: str  # 例如: 'content', 'reasoning', 'error', 'done', 'usage'
    content: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
