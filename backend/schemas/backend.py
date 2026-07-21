from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.schemas.enums import BackendType
from backend.utils.path_safe import validate_path_safe_name

PASSWORD_MASK = "********"

class SSHConfigData(BaseModel):
    """SSH Backend 严格的配置结构"""
    hostname: str = Field(..., description="远程服务器 IP 或域名")
    port: int = Field(22, description="SSH 端口")
    username: str = Field(..., description="SSH 登录用户名")
    password: Optional[str] = Field(None, description="SSH 密码。如果不填，则使用系统的全局私钥进行免密登录")
    root_dir: str = Field("/", description="挂载的远程根目录")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的虚拟路径前缀列表，如 ['/workspace/src/', '/workspace/app/']")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的虚拟路径前缀列表")
    ignore_dirs: Optional[List[str]] = Field(None, description="遍历时忽略的目录，如 ['.git', 'node_modules']")


class APIConfigData(BaseModel):
    """API Backend 配置结构 - 客户端主动连接模式

    仅需 api_key。客户端会自动连接并注册。
    edit_whitelist / edit_blacklist / ignore_dirs 由服务端控制，通过每次命令下发到客户端。
    """
    api_key: str = Field(..., description="API 密钥，客户端连接时需要提供此密钥进行认证")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的虚拟路径前缀列表，如 ['/workspace/src/', '/workspace/app/']")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的虚拟路径前缀列表，如 ['/workspace/build/']")
    ignore_dirs: Optional[List[str]] = Field(None, description="遍历时忽略的目录名，如 ['node_modules', '.git']")


class ResourceConfigData(BaseModel):
    """Resource Backend 配置结构 - 将 Resource DB 文件夹树映射为虚拟文件系统

    挂载一个 FOLDER 类型的 Resource 作为 Agent 的 workspace root，
    其后代子树将被加载为虚拟文件系统供 Agent 读写。
    """
    resource_id: str = Field(..., description="挂载的资源文件夹 ID（FOLDER 类型 Resource）")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的虚拟路径前缀列表，如 ['/workspace/src/', '/workspace/app/']")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的虚拟路径前缀列表，如 ['/workspace/build/']")


class LocalConfigData(BaseModel):
    """Local Backend 配置结构 - 直接访问服务器本地文件系统

    将服务器本机文件系统映射为 Agent 的虚拟文件系统。
    root_dir 默认为当前用户目录。
    """
    root_dir: str = Field("~", description="映射的本地根目录，默认为用户 home 目录")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的虚拟路径前缀列表")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的虚拟路径前缀列表")
    ignore_dirs: Optional[List[str]] = Field(None, description="遍历时忽略的目录，如 ['.git', 'node_modules']")

class BackendConfigBase(BaseModel):
    name: str = Field(..., description="Backend 挂载路由名称 (仅限字母数字下划线)")
    description: Optional[str] = Field(None, description="描述")
    backendType: BackendType = Field(..., description="Backend 类型")
    configData: Dict[str, Any] = Field(..., description="配置数据")
    tools_config: Optional[Dict[str, Any]] = Field(
        None,
        description="工具配置，如 {\"execute\": {\"enabled\": false, \"require_review\": true}}"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        return validate_path_safe_name(v, label="Backend name")

    @field_validator('configData')
    @classmethod
    def validate_config_data(cls, v, info):
        backend_type = info.data.get('backendType')
        if backend_type == BackendType.SSH.value:
            if v.get("password") == PASSWORD_MASK:
                temp_v = v.copy()
                temp_v["password"] = "dummy"
                SSHConfigData(**temp_v)
            else:
                SSHConfigData(**v)
        elif backend_type == BackendType.API.value:
            if v.get("api_key") == PASSWORD_MASK:
                temp_v = v.copy()
                temp_v["api_key"] = "dummy"
                APIConfigData(**temp_v)
            else:
                APIConfigData(**v)
        elif backend_type == BackendType.RESOURCE.value:
            ResourceConfigData(**v)
        elif backend_type == BackendType.LOCAL.value:
            LocalConfigData(**v)
        return v

    @model_validator(mode='after')
    def validate_edit_list_mutual_exclusion(self):
        """白名单和黑名单互斥，不能同时设置。"""
        cd = self.configData or {}
        wl = cd.get("edit_whitelist")
        bl = cd.get("edit_blacklist")
        if wl and bl and len(wl) > 0 and len(bl) > 0:
            raise ValueError(
                "edit_whitelist and edit_blacklist are mutually exclusive. "
                "Please set at most one of them."
            )
        return self

class BackendConfigCreate(BackendConfigBase):
    pass

class BackendConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    configData: Optional[Dict[str, Any]] = None
    tools_config: Optional[Dict[str, Any]] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            return validate_path_safe_name(v, label="Backend name")
        return v

class BackendConfigResponse(BackendConfigBase):
    id: str
    createdAt: datetime
    updatedAt: datetime
    class Config:
        from_attributes = True

class SSHPublicKeyResponse(BaseModel):
    public_key: str = Field(..., description="系统全局 SSH 公钥")

class SSHTestRequest(BaseModel):
    backend_id: Optional[str] = Field(None, description="如果基于已保存的配置测试，传入 ID")
    configData: Dict[str, Any] = Field(..., description="前端表单中的配置数据")

class SSHTestResponse(BaseModel):
    success: bool = Field(..., description="测试是否成功")
    message: str = Field(..., description="成功或失败的详细信息")


class SSHLsEntry(BaseModel):
    """远程目录列表中的单个条目"""
    path: str = Field(..., description="路径（相对于 root_dir，以 / 开头；目录以 / 结尾）")
    is_dir: bool = Field(False, description="是否为目录")
    size: int = Field(0, description="文件大小（字节）")
    modified_at: str = Field("", description="ISO-8601 修改时间戳")


class SSHLsRequest(BaseModel):
    """[内部] SSH 目录列表请求 — 由 UnifiedLsRequest 构造"""
    path: str = Field("/")
    hostname: str = Field(...)
    port: int = Field(22)
    username: str = Field(...)
    password: Optional[str] = Field(None)
    root_dir: str = Field("/")
    backend_id: Optional[str] = Field(None)


class LocalLsRequest(BaseModel):
    """列出本地文件系统目录的请求"""
    path: str = Field("/", description="要列出的路径（相对于 root_dir，如 / 表示 root_dir 本身）")
    root_dir: str = Field("~", description="本地根目录（如 /home/user 或 C:\\Users\\xxx）")


class LocalLsResponse(BaseModel):
    """列出本地文件系统目录的响应"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field("", description="成功或失败的详细信息")
    entries: Optional[List[SSHLsEntry]] = Field(None, description="目录条目列表")
    parent_path: Optional[str] = Field(None, description="父目录路径")


class UnifiedLsRequest(BaseModel):
    """统一的目录列表请求，根据 backend_type 分发到不同实现"""
    backend_type: BackendType = Field(..., description="Backend 类型：ssh / local")
    path: str = Field("/", description="要列出的路径")
    root_dir: str = Field("/", description="根目录（SSH: 远程根目录 / Local: 本地根目录）")
    # SSH 专用（Local 忽略）
    hostname: Optional[str] = Field(None, description="SSH: 远程服务器 IP 或域名")
    port: int = Field(22, description="SSH: 端口")
    username: Optional[str] = Field(None, description="SSH: 登录用户名")
    password: Optional[str] = Field(None, description="SSH: 密码")
    # 通用
    backend_id: Optional[str] = Field(None, description="已保存的 Backend ID，用于 SSH 密码脱敏合并")
