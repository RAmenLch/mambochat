"""MamboChat Agent 导出包（.mamboagent）格式模型。

对应 doc/agent-package-spec.md 第 3-5 节。
所有模型以 extra='ignore' 解析未知字段（规范 §8），保证向前兼容。
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────── 数据段 ───────────────────────────

class PackageModel(BaseModel):
    """providers[].models[] 中的模型"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    modelId: str
    name: str
    meta_config: Optional[Dict[str, Any]] = None
    model_type: str = "chat"
    starred: bool = False


class PackageProvider(BaseModel):
    """providers[] 中的服务商"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    apiHost: str
    use_proxy: bool = False
    worker_type: str = "openai"
    apiKeyMissing: bool = True
    models: List[PackageModel] = Field(default_factory=list)


class PackageFileRef(BaseModel):
    """版本中文件型内容的元信息 + blob 引用"""
    model_config = ConfigDict(extra='ignore')

    filename: str
    mimeType: str
    size: int
    blobId: str


class PackageResourceVersion(BaseModel):
    """resources[].versions[] 中的版本"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    sortOrder: int = 0
    commitMessage: Optional[str] = None
    contentType: Literal["text", "file"] = "text"
    content: Optional[str] = None
    file: Optional[PackageFileRef] = None
    attributes: Optional[Dict[str, Any]] = None


class PackageResource(BaseModel):
    """resources[] 中的节点（虚拟容器或真实资源）"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    description: Optional[str] = None
    itemType: str
    resourceType: Optional[str] = None
    parentId: Optional[str] = None
    sortOrder: int = 0
    kb_id: Optional[str] = None
    kb_config: Optional[Dict[str, Any]] = None
    latestVersionId: Optional[str] = None
    versions: List[PackageResourceVersion] = Field(default_factory=list)


class PackageAgent(BaseModel):
    """agents[] 中的 Agent（不含 parentId / sortOrder / 时间戳，规范 §5.2）"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    description: Optional[str] = None
    itemType: str = "agent"
    AgentType: str = "Mambo"
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict[str, Any]] = None
    agentParameters: Optional[Dict[str, Any]] = None
    aiModelId: Optional[str] = None
    agentAvatarId: Optional[str] = None
    resourcePromptList: List[str] = Field(default_factory=list)
    enabledMcpIds: List[str] = Field(default_factory=list)
    subAgents: List[str] = Field(default_factory=list)
    backendIds: List[str] = Field(default_factory=list)
    defaultBackendId: Optional[str] = None


class PackageMcpServer(BaseModel):
    """mcpServers[]（不导出 env/headers 及运行时状态字段，规范 §5.5）"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    description: Optional[str] = None
    transportType: str = "stdio"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    cwd: Optional[str] = None
    url: Optional[str] = None
    timeout: Optional[float] = None
    sse_read_timeout: Optional[float] = None
    isEnabled: bool = True


class PackageBackend(BaseModel):
    """backends[]（仅 backendType == "resource"，规范 §5.6）"""
    model_config = ConfigDict(extra='ignore')

    sourceId: str
    name: str
    description: Optional[str] = None
    backendType: str
    configData: Dict[str, Any] = Field(default_factory=dict)
    tools_config: Optional[Dict[str, Any]] = None


class PackageBlob(BaseModel):
    """blobs[] 载荷段"""
    model_config = ConfigDict(extra='ignore')

    blobId: str
    filename: str
    mimeType: str
    size: int
    encoding: Literal["base64"] = "base64"
    data: str


class AgentPackage(BaseModel):
    """顶层包结构（规范 §3）"""
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    schema_ref: Optional[str] = Field(None, alias="$schema")
    format: str
    formatVersion: str
    mambochatVersion: str
    exportedAt: datetime
    description: Optional[str] = None
    agents: List[PackageAgent] = Field(default_factory=list)
    providers: List[PackageProvider] = Field(default_factory=list)
    resources: List[PackageResource] = Field(default_factory=list)
    mcpServers: List[PackageMcpServer] = Field(default_factory=list)
    backends: List[PackageBackend] = Field(default_factory=list)
    blobs: List[PackageBlob] = Field(default_factory=list)


# ─────────────────────────── 导入相关响应模型 ───────────────────────────

class RenameSuggestion(BaseModel):
    """冲突改名建议"""
    entity_type: str  # 'agent' | 'provider' | 'backend' | 'resource_namespace' | 'subagent_folder'
    source_id: str
    original_name: str
    new_name: str


class ProviderBrief(BaseModel):
    """缺少 apiKey 的服务商（导入端恒列出全部服务商，规范 §4.2）"""
    source_id: str
    name: str


class ResourcePreviewNode(BaseModel):
    """导入目录树预览节点"""
    name: str
    itemType: str
    resourceType: Optional[str] = None
    children: List["ResourcePreviewNode"] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    """dry-run 预检结果（规范 §7.1 步 4）"""
    importable: bool = True
    format_version: str
    mambochat_version: str
    exported_at: datetime
    description: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    rename_suggestions: List[RenameSuggestion] = Field(default_factory=list)
    providers_missing_api_key: List[ProviderBrief] = Field(default_factory=list)
    resource_tree: List[ResourcePreviewNode] = Field(default_factory=list)


class CreatedEntity(BaseModel):
    """本次导入会话中已创建的实体"""
    entity_type: str  # 'provider' | 'resource' | 'mcp' | 'backend' | 'agent' | 'file'
    source_id: str
    new_id: str


class ImportReport(BaseModel):
    """正式导入报告（规范 §7.1 步 6 / §7.4）"""
    import_session_id: str
    success: bool
    main_agent_id: Optional[str] = None
    created: List[CreatedEntity] = Field(default_factory=list)
    failed_phase: Optional[str] = None
    failed_entity: Optional[str] = None
    error: Optional[str] = None
    providers_missing_api_key: List[ProviderBrief] = Field(default_factory=list)


class CleanupReport(BaseModel):
    """清理接口响应"""
    cleaned: List[str] = Field(default_factory=list)


ResourcePreviewNode.model_rebuild()
