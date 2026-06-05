# backend/services/generation/core/llm_io.py

from datetime import datetime
from typing import List, Dict, Any, Optional, Union

from mambo_agents.middleware.summarization import SummarizationEvent
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.tools import BaseTool

from backend.schemas.enums import AgentTypeEnum


# --- 消息结构化 Schema ---
# 统一 ORM Message/SubMessage 与合成消息的类型，消除 builders 层的鸭子类型

class SubMessageSchema(BaseModel):
    """子消息的规范类型，兼容 ORM SubMessage 和合成对象。"""
    model_config = ConfigDict(from_attributes=True)

    type: str
    content: str
    config: Optional[str] = None
    createdAt: Optional[datetime] = None
    sortOrder: int = 0
    id: Optional[str] = None
    status: Optional[str] = None


class MessageSchema(BaseModel):
    """消息的规范类型，兼容 ORM Message 和合成对象。"""
    model_config = ConfigDict(from_attributes=True)

    role: str
    sub_messages: List[SubMessageSchema] = Field(default_factory=list)
    id: Optional[str] = None
    parentId: Optional[str] = None  # 用于沿父链查找分支 checkpoint


# --- 生成管道数据结构 ---

class SkillFileConfig(BaseModel):
    """
    技能包内部文件的配置信息。
    """
    file_path: str = Field(..., description="文件相对于 SKILL 根目录的相对路径 (例如: SKILL_A/src/main.py)")
    file_id: str = Field(..., description="底层物理文件的 ID (File.id)")
    content: Optional[str] = Field(None, description="预加载的文件纯文本内容")

class SkillConfig(BaseModel):
    """
    技能包的整体配置信息。
    """
    name: str = Field(..., description="SKILL 的名称")
    files: List[SkillFileConfig] = Field(default_factory=list, description="该 SKILL 下的所有文件列表")


class ModelConfig(BaseModel):
    """
    大语言模型本身的运行配置。
    包含模型标识、连接信息以及生成参数。纯数据结构，不含任何业务逻辑。
    """
    model_id: str = Field(..., description="模型唯一标识符")
    api_host: str = Field(..., description="API 请求地址")
    api_key: str = Field(..., description="API 密钥")
    proxy_url: Optional[str] = Field(None, description="代理地址，例如 http://127.0.0.1:7890")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="模型的生成参数 (如 temperature, top_p, stream 等)"
    )
    timeout: int = Field(60, description="请求超时时间(秒)")
    max_retries: int = Field(0, description="模型请求最大重试次数, 0表示不配置, 将使用全局默认值")
    stream_chunk_timeout: Optional[float] = Field(
        None,
        description="流式响应 chunk 间超时时间(秒)。为 None 或 0 时禁用。"
                    "对于图片生成等耗时模型，建议设置为较大值（如 600）或 None。"
    )
    context_length: Optional[int] = Field(
        None,
        description="模型最大上下文窗口 (tokens)，用于 summarization fraction 模式。"
                    "从 AIModel.meta_config.context_length 读取。"
    )


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
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        if content:
            self.messages.insert(0, {"role": "system", "content": content})
        return self

class RunTimeConfig(BaseModel):
    chat_id: str = Field(..., description="当前生成的 Chat ID，用作 LangGraph 的 thread_id")
    message_id: Optional[str] = Field(None, description="当前轮的Message ID")
    manager_name: Optional[str] = Field(None, description="当前manager名称")
    branch_checkpoint_id: Optional[str] = Field(
        None,
        description="分支起点 checkpoint_id。设置后 LangGraph 会进行时间旅行，从该 checkpoint 分叉",
    )


class AgentConfig(BaseModel):
    """
    Agent 运行与调度配置。
    包含专属模型配置、工具列表、HITL(人机交互)中断配置、线程管理、技能包挂载等。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(default="default-agent", description="Agent 名称")
    description: str = Field(default="", description="Agent 描述，用于父代理路由")
    system_prompt: str = Field(default="", description="Agent 的系统提示词")

    agent_type: AgentTypeEnum = Field(default=AgentTypeEnum.MAMBO, description="Agent 的类型标识")
    llm_config: Optional[ModelConfig] = Field(default=None, description="该Agent专属的模型配置")
    mounted_backends: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="挂载的 Backend 配置列表 (包含类型、路由名称和连接参数)"
    )
    default_backend_id: Optional[str] = Field(
        None,
        description="用户选择的默认 Backend ID，该 backend 将成为 default"
    )
    tools: Optional[List[BaseTool]] = Field(None, description="挂载给 Agent 的工具列表")

    skills: Optional[List[SkillConfig]] = Field(
        default=None,
        description="挂载给 Agent 的外部技能包 (SKILL) 列表"
    )
    sub_configs: Optional[List['AgentConfig']] = Field(
        default=None,
        description="子代理的配置树"
    )
    hitl_interrupt_on: Dict[str, bool] = Field(
        default_factory=dict,
        description="需要人工审核中断的工具名称映射，例如 {'execute_sql': True}"
    )
    resume_payload: Optional[Dict[str, Any]] = Field(
        None,
        description="用于从 HITL 中断中恢复的决策载荷"
    )
    recover_from_error: bool = Field(
        False,
        description="是否从错误中恢复（传入 input=None + thread_id 利用 LangGraph checkpoint 继续执行）"
    )

    # --- Mambo-Agent 专属配置 ---
    include_general_purpose: bool = Field(
        default=False,
        description="是否启用 general-purpose 子代理（仅 Mambo Agent 有效）"
    )
    enable_summarization: bool = Field(
        default=False,
        description="是否启用对话摘要/压缩（仅 Mambo Agent 有效）"
    )
    summarization_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="摘要配置（仅 enable_summarization=True 时有效）。"
                    "结构: {trigger_type, trigger_value, keep_type, keep_value, offload_to_backend}"
    )


class LLMInput(BaseModel):
    """
    V2 版本的标准 LLM 输入对象。
    聚合了消息上下文和 Agent 调度配置（内含模型配置），作为 Worker 的唯一输入参数。
    """
    context: MessageContext
    agent_config: AgentConfig
    run_time_config: RunTimeConfig



class SummarizationEventInfo(BaseModel):
    """Captures a summarization/compaction event emitted by the graph worker.

    Attributes:
        last_zip_message: The last message *before* the summarization cutoff —
            i.e. ``state_messages[cutoff_index - 1]``.  Used by the manager to
            derive ``target_msg_id`` / ``target_sub_msg_id`` for persisting the
            ``ZipHistory`` sub-message.
        event: The raw ``SummarizationEvent`` dict produced by the
            summarization middleware, containing ``cutoff_index``,
            ``summary_message``, and ``file_path``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_zip_message: BaseMessage
    event: SummarizationEvent