from langchain_core.tools import BaseTool
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
    tools: Optional[List[BaseTool]] = None
    tool_choice: Optional[Union[str, Dict]] = None
    timeout: int = 60  # 默认超时时间

    hitl_interrupt_on: Dict[str, bool] = Field(default_factory=dict, description="需要人工审核中断的工具名称映射")
    thread_id: str = Field(..., description="当前生成的 Assistant 消息 ID，用作 LangGraph 的 thread_id")
    resume_payload: Optional[Dict[str, Any]] = None


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