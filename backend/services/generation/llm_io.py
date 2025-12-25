# backend/services/generation/llm_io.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union


# backend/services/generation/llm_io.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union


class LLMInput(BaseModel):
    """
    标准化的 LLM 输入对象。
    包含发送给 Worker 所需的所有信息：模型、消息、参数、连接配置等。
    """
    model_id: str
    messages: List[Dict[str, Any]]
    # noinspection PyDataclass
    parameters: Dict[str, Any] = Field(default_factory=dict)
    api_host: str
    api_key: str
    proxy_url: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict]] = None
    timeout: int = 60  # 默认超时时间

    def set_system_prompt(self, content: str):
        """设置或更新系统提示词，确保只有一个系统消息且在首位"""
        # 移除现有的系统消息
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        if content:
            self.messages.insert(0, {"role": "system", "content": content})
        return self

    def set_parameter(self, key: str, value: Any):
        """设置或覆盖模型参数"""
        self.parameters[key] = value
        return self

    def to_payload(self) -> Dict[str, Any]:
        """获取最终发送给 Worker 的完整请求体"""
        payload = {
            "model": self.model_id,
            "messages": self.messages,
            **self.parameters
        }
        if self.tools:
            payload["tools"] = self.tools
        if self.tool_choice:
            payload["tool_choice"] = self.tool_choice
        return payload

class WorkerOutput(BaseModel):
    """
    一个标准化的、与具体模型无关的LLM响应块。
    由 Worker 创建，由 Manager 消费。
    """
    type: str  # 例如: 'content', 'reasoning', 'error', 'done', 'usage'
    content: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
