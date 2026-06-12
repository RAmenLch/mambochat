# backend/schemas/agent.py

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any

# [修复] 为 AgentType 设置别名 AgentTypeEnum，防止与字段名冲突
from backend.schemas.enums import AgentItemType, AgentTypeEnum, MoveAction
from backend.utils.path_safe import validate_path_safe_name


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
    agentParameters: Optional[Dict[str, Any]] = Field(None, description="Agent 专属配置参数")

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
    AgentType: Optional[AgentTypeEnum] = None  # [修复] 使用别名
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict[str, Any]] = None
    agentParameters: Optional[Dict[str, Any]] = None
    aiModelId: Optional[str] = None
    agentAvatarId: Optional[str] = None
    resourcePromptList: Optional[List[str]] = None
    enabledMcpIds: Optional[List[str]] = None
    subAgents: Optional[List[str]] = None
    backendIds: Optional[List[str]] = None
    defaultBackendId: Optional[str] = None
    memoryResourceIds: Optional[List[str]] = None

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
