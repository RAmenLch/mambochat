from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any

from backend.database import get_db
from backend.crud import backend_crud
from backend.schemas.enums import BackendType
from backend.schemas.backend import (
    BackendConfigCreate,
    BackendConfigUpdate,
    BackendConfigResponse,
    SSHPublicKeyResponse,
    SSHTestRequest,
    SSHTestResponse,
    SSHLsRequest,
    SSHLsResponse,
    PASSWORD_MASK,
    SSHConfigData,
    APIConfigData
)
from backend.utils.ssh_utils import get_or_create_system_ssh_key
from backend.services.generation.agent.ssh_backend import PureSFTPBackend

router = APIRouter(prefix="/backends", tags=["Backends"])


# --- 辅助函数：密码脱敏 ---
def _mask_password(db_obj: backend_crud.BackendConfig) -> BackendConfigResponse:
    """将数据库对象转换为 Response，并脱敏密码和 API Key"""
    resp = BackendConfigResponse.model_validate(db_obj)
    if resp.backendType == BackendType.SSH.value and resp.configData:
        if resp.configData.get("password"):
            resp.configData["password"] = PASSWORD_MASK
    elif resp.backendType == BackendType.API.value and resp.configData:
        if resp.configData.get("api_key"):
            resp.configData["api_key"] = PASSWORD_MASK
    return resp


# --- 辅助函数：密码合并 ---
def _merge_password(incoming_config: Dict[str, Any], existing_config: Dict[str, Any]) -> Dict[str, Any]:
    """处理前端传来的 configData，解析密码掩码"""
    merged = incoming_config.copy()
    if merged.get("password") == PASSWORD_MASK:
        # 保持原有密码
        merged["password"] = existing_config.get("password")
    elif merged.get("password") == "":
        # 前端显式清空密码，意图使用免密
        merged["password"] = None
    return merged


# --- 核心测试逻辑 ---
async def _test_ssh_connection(config_dict: Dict[str, Any]) -> SSHTestResponse:
    try:
        # 1. 结构化校验
        ssh_config = SSHConfigData(**config_dict)

        # 2. 确定私钥
        priv_key_path = None
        if not ssh_config.password:
            priv_key_path, _ = get_or_create_system_ssh_key()

        # 3. 实例化 Backend 并尝试连接
        backend = PureSFTPBackend(
            hostname=ssh_config.hostname,
            port=ssh_config.port,
            username=ssh_config.username,
            password=ssh_config.password,
            key_filename=priv_key_path,
            root_dir=ssh_config.root_dir
        )

        # _connect() 会抛出 AuthenticationException, SSHException 等
        backend._connect()
        backend.close()

        return SSHTestResponse(success=True, message="连接成功")
    except Exception as e:
        return SSHTestResponse(success=False, message=f"连接失败: {str(e)}")


@router.post("/ssh/test", response_model=SSHTestResponse, summary="测试 SSH 连接")
async def test_ssh_connection(request: SSHTestRequest, db: AsyncSession = Depends(get_db)):
    """
    测试 SSH 连接。
    支持未保存测试（直接传 configData）和半保存测试（传 backend_id 和表单 configData）。
    """
    test_config = request.configData.copy()

    # 如果提供了 backend_id，说明是修改状态下的测试，需要合并密码
    if request.backend_id:
        db_obj = await backend_crud.get_backend(db, request.backend_id)
        if db_obj and db_obj.backendType == BackendType.SSH.value:
            test_config = _merge_password(test_config, db_obj.configData)

    # 如果依然是掩码（比如乱传了 backend_id 但数据库没密码），清空以防报错
    if test_config.get("password") == PASSWORD_MASK:
        test_config["password"] = None

    return await _test_ssh_connection(test_config)


@router.post("/ssh/ls", response_model=SSHLsResponse, summary="列出远程 SSH 目录")
async def ssh_list_directory(request: SSHLsRequest, db: AsyncSession = Depends(get_db)):
    """
    列出远程服务器上的目录内容。

    用于前端目录选择器，允许用户在配置 SSH Backend 时浏览远程文件系统，
    为 edit_whitelist / edit_blacklist 选择路径前缀。
    """
    # 密码脱敏合并：如果提供了 backend_id 且密码是掩码，从数据库获取真实密码
    password = request.password
    if request.backend_id:
        db_obj = await backend_crud.get_backend(db, request.backend_id)
        if db_obj and db_obj.backendType == BackendType.SSH.value:
            merged = _merge_password(
                {"password": password}, db_obj.configData
            )
            password = merged.get("password")
    if password == PASSWORD_MASK:
        password = None

    try:
        ssh_config = SSHConfigData(
            hostname=request.hostname,
            port=request.port,
            username=request.username,
            password=password,
            root_dir=request.root_dir,
        )

        priv_key_path = None
        if not ssh_config.password:
            priv_key_path, _ = get_or_create_system_ssh_key()

        backend = PureSFTPBackend(
            hostname=ssh_config.hostname,
            port=ssh_config.port,
            username=ssh_config.username,
            password=ssh_config.password,
            key_filename=priv_key_path,
            root_dir=ssh_config.root_dir,
        )

        list_path = request.path or "/"
        entries = backend.ls_info(list_path)

        # Determine parent path for navigation
        parent = None
        if list_path != "/":
            parent_dir = list_path.rstrip("/")
            if "/" in parent_dir:
                parent = parent_dir.rsplit("/", 1)[0] or "/"
            else:
                parent = "/"

        backend.close()

        return SSHLsResponse(
            success=True,
            message="",
            entries=[
                {
                    "path": e.get("path", ""),
                    "is_dir": e.get("is_dir", False),
                    "size": e.get("size", 0),
                    "modified_at": e.get("modified_at", ""),
                }
                for e in entries
            ],
            parent_path=parent,
        )
    except Exception as e:
        return SSHLsResponse(success=False, message=f"目录列表失败: {str(e)}")


@router.get("/ssh/public-key", response_model=SSHPublicKeyResponse, summary="获取系统全局 SSH 公钥")
async def get_ssh_public_key():
    """获取公钥，以便用户将其配置到远程服务器的 authorized_keys 中实现免密登录"""
    _, pub_key = get_or_create_system_ssh_key()
    return {"public_key": pub_key}


@router.post("/", response_model=BackendConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_backend(backend_in: BackendConfigCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(backend_crud.BackendConfig).filter_by(name=backend_in.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Backend name already exists")

    # 如果前端在创建时传了掩码或空字符串，处理一下
    if backend_in.backendType == BackendType.SSH.value:
        if backend_in.configData.get("password") in [PASSWORD_MASK, ""]:
            backend_in.configData["password"] = None
    elif backend_in.backendType == BackendType.API.value:
        if backend_in.configData.get("api_key") in [PASSWORD_MASK, ""]:
            backend_in.configData["api_key"] = None

    db_obj = await backend_crud.create_backend(db, backend_in)
    return _mask_password(db_obj)


@router.get("/", response_model=List[BackendConfigResponse])
async def read_backends(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    db_objs = await backend_crud.get_all_backends(db, skip=skip, limit=limit)
    return [_mask_password(obj) for obj in db_objs]


@router.get("/{backend_id}", response_model=BackendConfigResponse)
async def read_backend(backend_id: str, db: AsyncSession = Depends(get_db)):
    db_obj = await backend_crud.get_backend(db, backend_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Backend not found")
    return _mask_password(db_obj)


@router.put("/{backend_id}", response_model=BackendConfigResponse)
async def update_backend(backend_id: str, backend_in: BackendConfigUpdate, db: AsyncSession = Depends(get_db)):
    db_obj = await backend_crud.get_backend(db, backend_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Backend not found")

    # 名称查重
    if backend_in.name and backend_in.name != db_obj.name:
        existing = await db.execute(select(backend_crud.BackendConfig).filter_by(name=backend_in.name))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Backend name already exists")

    # 处理密码合并
    if backend_in.configData and db_obj.backendType == BackendType.SSH.value:
        backend_in.configData = _merge_password(backend_in.configData, db_obj.configData)

    # 处理 API Key 合并
    if backend_in.configData and db_obj.backendType == BackendType.API.value:
        if backend_in.configData.get("api_key") == PASSWORD_MASK:
            backend_in.configData["api_key"] = db_obj.configData.get("api_key")
        elif backend_in.configData.get("api_key") == "":
            backend_in.configData["api_key"] = None

    updated_obj = await backend_crud.update_backend(db, backend_id, backend_in)
    return _mask_password(updated_obj)


@router.post("/{backend_id}/duplicate", response_model=BackendConfigResponse, status_code=status.HTTP_201_CREATED, summary="复制 Backend（副本）")
async def duplicate_backend(backend_id: str, db: AsyncSession = Depends(get_db)):
    """基于现有 Backend 创建一个副本，名称自动添加 ' - 副本' 后缀"""
    import re
    import copy

    db_obj = await backend_crud.get_backend(db, backend_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Backend not found")

    # 解析基准名
    base_name = db_obj.name
    match = re.match(r'^(.*?)(?:-副本(?:\d+)?)?$', base_name)
    if match:
        base_name = match.group(1).strip()

    # 查找已有副本
    all_backends = await backend_crud.get_all_backends(db, skip=0, limit=10000)
    existing_nums: list = []
    pattern = re.compile(r'^' + re.escape(base_name) + r'-副本(\d+)?$')
    for b in all_backends:
        m = pattern.match(b.name)
        if m:
            num = int(m.group(1)) if m.group(1) else 1
            existing_nums.append(num)

    if not existing_nums:
        new_name = f"{base_name}-副本"
    else:
        next_num = max(existing_nums) + 1
        new_name = f"{base_name}-副本{next_num}"

    # 构造副本配置（完整复制）
    config_data = copy.deepcopy(db_obj.configData)

    new_backend = BackendConfigCreate(
        name=new_name,
        description=db_obj.description,
        backendType=db_obj.backendType,
        configData=config_data,
        tools_config=db_obj.tools_config,
    )

    db_new = await backend_crud.create_backend(db, new_backend)
    return _mask_password(db_new)


@router.delete("/{backend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backend(backend_id: str, db: AsyncSession = Depends(get_db)):
    success = await backend_crud.delete_backend(db, backend_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backend not found")
