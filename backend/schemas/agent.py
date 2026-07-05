# backend/schemas/agent.py

from pydantic import BaseModel, Field, field_validator
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


class VersionControlConfigSchema(BaseModel):
    """版本控制中间件配置"""
    enabled: bool = Field(False, description="是否启用版本控制（文件变更历史自动备份）")
    auto_snapshot: bool = Field(True, description="是否自动在文件写入/编辑/删除时创建快照")


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
    version_control: Optional[VersionControlConfigSchema] = Field(None, description="版本控制配置")


class HitlToolInfo(BaseModel):
    """HITL 可审核工具信息（用于前端审核范围选择器）"""
    name: str = Field(..., description="工具名")
    source: str = Field(..., description="工具来源: 'mcp' 或 'backend'")


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
