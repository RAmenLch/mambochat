from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.schemas.enums import BackendType
import re

PASSWORD_MASK = "********"

FORBIDDEN_BACKEND_NAMES = {"skills", "memories", "state", "root", "tmp", "temp"}

class SSHConfigData(BaseModel):
    """SSH Backend 严格的配置结构"""
    hostname: str = Field(..., description="远程服务器 IP 或域名")
    port: int = Field(22, description="SSH 端口")
    username: str = Field(..., description="SSH 登录用户名")
    password: Optional[str] = Field(None, description="SSH 密码。如果不填，则使用系统的全局私钥进行免密登录")
    root_dir: str = Field("/", description="挂载的远程根目录")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的文件通配符列表，如 ['*.py', '*.txt']")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的文件通配符列表")
    ignore_dirs: Optional[List[str]] = Field(None, description="遍历时忽略的目录，如 ['.git', 'node_modules']")


class APIConfigData(BaseModel):
    """API Backend 配置结构 - 客户端主动连接模式

    仅需 api_key。root_dir / ignore_dirs 由客户端启动时通过 --root-dir / --ignore-dirs 参数指定。
    edit_whitelist 和 edit_blacklist 由服务端控制，用于限制 LLM 可编辑的文件范围。
    """
    api_key: str = Field(..., description="API 密钥，客户端连接时需要提供此密钥进行认证")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的文件通配符列表")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的文件通配符列表")


class ResourceConfigData(BaseModel):
    """Resource Backend 配置结构 - 将 Resource DB 文件夹树映射为虚拟文件系统

    挂载一个 FOLDER 类型的 Resource 作为 Agent 的 workspace root，
    其后代子树将被加载为虚拟文件系统供 Agent 读写。
    """
    resource_id: str = Field(..., description="挂载的资源文件夹 ID（FOLDER 类型 Resource）")
    edit_whitelist: Optional[List[str]] = Field(None, description="允许编辑的文件通配符列表")
    edit_blacklist: Optional[List[str]] = Field(None, description="禁止编辑的文件通配符列表")

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
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Backend name 只能包含字母、数字和下划线，因为它将作为路径路由")
        if v.lower() in FORBIDDEN_BACKEND_NAMES:
            raise ValueError(f"Backend name 不能使用系统保留字: {', '.join(FORBIDDEN_BACKEND_NAMES)}")
        return v

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
        return v

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
        if v:
            if not re.match(r"^[a-zA-Z0-9_]+$", v):
                raise ValueError("Backend name 只能包含字母、数字和下划线")
            if v.lower() in FORBIDDEN_BACKEND_NAMES:
                raise ValueError(f"Backend name 不能使用系统保留字: {', '.join(FORBIDDEN_BACKEND_NAMES)}")
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
