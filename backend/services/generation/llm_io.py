# backend/services/generation/llm_io.py

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.tools import BaseTool

from backend.schemas.enums import AgentTypeEnum


class ModelConfig(BaseModel):
    """
    大语言模型本身的运行配置。
    包含模型标识、连接信息以及生成参数。
    """
    model_id: str = Field(..., description="模型唯一标识符")
    api_host: str = Field(..., description="API 请求地址")
    api_key: str = Field(..., description="API 密钥")
    proxy_url: Optional[str] = Field(None, description="代理地址，例如 http://127.0.0.1:7890")
    parameters: Dict[str, Any] = Field(default_factory=dict,
                                       description="模型的生成参数 (如 temperature, top_p, stream 等)")
    timeout: int = Field(60, description="请求超时时间(秒)")


class MessageContext(BaseModel):
    """
    上下文消息配置。
    包含经过过滤、切片、多模态转换后的标准 LLM 消息列表。
    """
    messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="标准化的 LLM 消息列表。要求包含 'role' 和 'content'，可能包含 'tool_calls' 等扩展字段。"
    )

    def set_system_prompt(self, content: str) -> "MessageContext":
        """设置或更新系统提示词，确保只有一个系统消息且在首位"""
        # 移除现有的系统消息
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        if content:
            self.messages.insert(0, {"role": "system", "content": content})
        return self


class AgentConfig(BaseModel):
    """
    Agent 运行与调度配置。
    包含工具列表、HITL(人机交互)中断配置、线程管理等。
    """
    # 【注意这里】：这里必须是 model_config，这是 Pydantic V2 的系统保留字，用来配置模型行为
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_type: AgentTypeEnum = Field(default=AgentTypeEnum.REACT, description="Agent 的类型标识")
    tools: Optional[List[BaseTool]] = Field(None, description="挂载给 Agent 的工具列表")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(None, description="强制工具调用选择")

    hitl_interrupt_on: Dict[str, bool] = Field(
        default_factory=dict,
        description="需要人工审核中断的工具名称映射，例如 {'execute_sql': True}"
    )
    thread_id: str = Field(..., description="当前生成的 Assistant 消息 ID，用作 LangGraph 的 thread_id")
    resume_payload: Optional[Dict[str, Any]] = Field(
        None,
        description="用于从 HITL 中断中恢复的决策载荷"
    )


class LLMInput(BaseModel):
    """
    V2 版本的标准 LLM 输入对象。
    将模型配置、消息上下文、Agent 调度配置彻底解耦。
    """
    llm_config: ModelConfig
    context: MessageContext
    agent_config: AgentConfig

