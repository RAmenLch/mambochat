# backend/schemas/agent.py

from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal

# [修复] 为 AgentType 设置别名 AgentTypeEnum，防止与字段名冲突
from backend.schemas.enums import AgentItemType, AgentTypeEnum, MoveAction
from backend.utils.path_safe import validate_path_safe_name


# ─────────────────────────── agentParameters 结构化子模型 ───────────────────────────

class SummarizationConfigSchema(BaseModel):
    """对话摘要/压缩配置"""
    trigger_type: Literal["fraction", "tokens", "messages"] = Field("tokens", description="触发类型")
    trigger_value: float = Field(180000.0, description="触发阈值")
    keep_type: Literal["fraction", "tokens", "messages"] = Field("messages", description="保留类型")
    keep_value: float = Field(20.0, description="保留数量")
    offload_to_backend: bool = Field(False, description="是否卸载到 Backend")


class SecurityReviewConfigSchema(BaseModel):
    """AI 安全审核配置的 API Schema"""
    enabled: bool = Field(default=False)
    model_id: Optional[str] = Field(None)
    system_prompt: Optional[str] = Field(None)
    review_tools: Optional[List[str]] = Field(None)
    agent_max_steps: Optional[int] = Field(None, description="审核 agent 最大步数（仅 agent 模式生效），缺省使用默认值 10")


class VersionControlConfigSchema(BaseModel):
    """版本控制中间件配置"""
    enabled: bool = Field(False, description="是否启用版本控制（文件变更历史自动备份）")
    auto_snapshot: bool = Field(True, description="是否自动在文件写入/编辑/删除时创建快照")


class MultimodalDescriberConfigSchema(BaseModel):
    """多模态描述配置：为每个模态独立绑定一个支持该模态的模型。

    主模型原生支持的模态会透传（不经过描述模型）；绑定模型后，主模型不支持的
    对应模态文件会先由描述模型生成描述文本；未绑定任何模型的模态将返回显式
    拒绝文本，避免多模态内容直通模型 API 报错。
    """
    enabled: bool = Field(False, description="是否启用多模态描述")
    image_model_id: Optional[str] = Field(None, description="图片描述模型 ID")
    audio_model_id: Optional[str] = Field(None, description="音频描述模型 ID")
    video_model_id: Optional[str] = Field(None, description="视频描述模型 ID")
    file_model_id: Optional[str] = Field(None, description="文档(PDF/PPT等)描述模型 ID")


class GoalLoopConditionSchema(BaseModel):
    """任务循环完成条件：某工具在当前轮内至少调用 times 次，且参数全部匹配才算一次有效调用"""
    tool: str = Field(..., description="工具名")
    times: int = Field(1, ge=1, description="至少调用次数")
    args: Optional[Dict[str, Any]] = Field(None, description="参数匹配（多个参数需全部匹配）")


class GoalLoopConfigSchema(BaseModel):
    """任务循环配置

    mode=llm    ：交给 AI 自己规划目标，自动多轮执行直至完成/卡住/轮数用尽（适合长程任务）
    mode=preset ：按用户设定的目标与完成条件循环，每轮强制围绕目标执行（全部条件满足才结束）
    """
    mode: Literal["llm", "preset"] = Field("llm", description="循环模式: llm=交给AI自己规划 / preset=按我的规则执行")
    max_rounds: int = Field(256, ge=1, description="轮数上限，到达后强制停止")
    objective: Optional[str] = Field(None, description="每轮目标（preset 必填）")
    conditions: Optional[List[GoalLoopConditionSchema]] = Field(None, description="完成条件（preset 用，全部满足才结束）")
    blocked_threshold: Optional[int] = Field(None, ge=1, description="至少工作满该轮数才允许宣告卡住（llm 用，默认 3）")

    @model_validator(mode="after")
    def _validate_mode_fields(self):
        if self.mode == "preset":
            if not self.objective or not self.objective.strip():
                raise ValueError("mode='preset' 需要非空的 objective")
            if self.blocked_threshold not in (None, 3):
                raise ValueError("blocked_threshold 仅在 mode='llm' 时可用")
        else:
            if self.objective is not None:
                raise ValueError("objective 仅在 mode='preset' 时可用")
            if self.conditions:
                raise ValueError("conditions 仅在 mode='preset' 时可用")
        return self


class MamboAgentParametersSchema(BaseModel):
    """Mambo Agent 专属参数（持久化到 Agent.agentParameters JSON 列）"""
    include_general_purpose: bool = Field(False, description="是否启用通用子代理")
    enable_planning: bool = Field(True, description="是否启用计划中间件")
    enable_memory: bool = Field(False, description="是否启用长期记忆")
    enable_summarization: bool = Field(False, description="是否启用对话摘要")
    enable_show: bool = Field(True, description="是否启用 show 工具（展示文件/图片给用户）")
    memory_resource_ids: List[str] = Field(default_factory=list, description="记忆资源ID列表")
    summarization_config: Optional[SummarizationConfigSchema] = Field(None, description="摘要详细配置")
    security_review: Optional[SecurityReviewConfigSchema] = Field(None, description="AI 安全审核配置")
    multimodal_describer: Optional[MultimodalDescriberConfigSchema] = Field(None, description="多模态描述配置")
    version_control: Optional[VersionControlConfigSchema] = Field(None, description="版本控制配置")
    goal_loop: Optional[GoalLoopConfigSchema] = Field(None, description="任务循环配置")
    mcp_direct_tool_threshold: int = Field(15, description="MCP 工具数量阈值：低于此值时直接暴露工具，否则使用 meta-tool 包装模式")


class HitlToolInfo(BaseModel):
    """HITL 可审核工具信息（用于前端审核范围选择器）"""
    name: str = Field(..., description="工具名")
    source: str = Field(..., description="工具来源: 'mcp' 或 'backend'")


class GoalLoopToolInfo(BaseModel):
    """任务循环「我的规则」工具建议信息（用于前端完成条件工具/参数选择器）。

    name 为执行侧真实工具名（MCP 工具为 ``服务器名__工具名`` 格式），
    与 mambo_agents goal_loop 的 tool_called_at_least 匹配方式保持一致。
    """
    name: str = Field(..., description="执行侧工具名")
    source: str = Field(..., description="工具来源: 'mcp' / 'backend' / 'builtin'")
    args: List[str] = Field(default_factory=list, description="参数名建议列表（来自工具 schema）")


# ─────────────────────────── Agent CRUD Schema ───────────────────────────

class AgentBase(BaseModel):
    """Agent 基础 Schema，定义通用字段与严格的数据类型"""
    name: str = Field(..., max_length=100, description="Agent 或文件夹名称")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        return validate_path_safe_name(v, label="Agent 名称")
    description: Optional[str] = Field(None, description="用户编辑的介绍")

    itemType: AgentItemType = Field(AgentItemType.AGENT, description="节点类型: 'agent' 或 'folder'")
    parentId: Optional[str] = Field(None, description="父文件夹的ID")
    sortOrder: int = Field(0, description="树状层级排序权重")

    AgentType: AgentTypeEnum = Field(AgentTypeEnum.REACT, description="Agent 初始化类型")

    systemPrompt: Optional[str] = Field(None, description="系统提示词")
    modelParameters: Optional[Dict[str, Any]] = Field(None, description="模型参数配置")
    agentParameters: Optional[MamboAgentParametersSchema] = Field(None, description="Agent 专属配置参数（结构化）")

    aiModelId: Optional[str] = Field(None, description="绑定的模型ID")
    agentAvatarId: Optional[str] = Field(None, description="关联的头像文件ID")

    resourcePromptList: Optional[List[str]] = Field(None, description="资源挂载ID列表")
    enabledMcpIds: Optional[List[str]] = Field(None, description="启用的 MCP 服务ID列表")
    subAgents: Optional[List[str]] = Field(None, description="子 Agent ID列表")
    backendIds: Optional[List[str]] = Field(default_factory=list, description="挂载的 Backend 配置 ID 列表")
    defaultBackendId: Optional[str] = Field(None, description="用户选择的默认 Backend ID")

class AgentCreate(AgentBase):
    """用于创建 Agent 的 Schema（继承 Base 保持一致）"""
    pass


class AgentUpdate(BaseModel):
    """用于更新 Agent 的 Schema，所有字段均为可选（支持局部更新）"""
    name: Optional[str] = Field(None, max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            return validate_path_safe_name(v, label="Agent 名称")
        return v
    description: Optional[str] = None
    itemType: Optional[AgentItemType] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None
    AgentType: Optional[AgentTypeEnum] = None
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict[str, Any]] = None
    agentParameters: Optional[MamboAgentParametersSchema] = None
    aiModelId: Optional[str] = None
    agentAvatarId: Optional[str] = None
    resourcePromptList: Optional[List[str]] = None
    enabledMcpIds: Optional[List[str]] = None
    subAgents: Optional[List[str]] = None
    backendIds: Optional[List[str]] = None
    defaultBackendId: Optional[str] = None
    # 以下为"转运字段"——Router 层会合并进 agentParameters，不直接落库
    memoryResourceIds: Optional[List[str]] = None
    securityReviewConfig: Optional[SecurityReviewConfigSchema] = None
    multimodalDescriberConfig: Optional[MultimodalDescriberConfigSchema] = None

class AgentResponse(AgentBase):
    """用于 API 响应的 Agent Schema，包含系统生成的标识和时间戳"""
    id: str
    createdAt: datetime
    updatedAt: datetime
    agentAvatarUrl: Optional[str] = Field(None, description="Agent 头像的访问URL（动态生成）")
    class Config:
        from_attributes = True


class AgentMoveRequest(BaseModel):
    """用于移动 Agent 树状节点的 Schema"""
    item_ids: List[str] = Field(..., description="被移动的 Agent 或文件夹ID列表")
    reference_id: str = Field(..., description="参考目标ID，'root'代表根目录")
    action: MoveAction = Field(..., description="移动行为: before, after, inside")
