# backend/routers/agent_management.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional

from backend.crud import agent_crud, file_crud, mcp_crud, backend_crud
from backend import schemas
from backend.models import agent_model
from backend.database import get_db
from backend.services.file_service import FileService
from backend.services.resource_service import validate_mounted_resources, validate_memory_resources
from backend.schemas.enums import FileManagementType, ToolReviewMode, BackendType


def _mcp_tool_name(server_name: str, tool_name: str) -> str:
    # 延迟导入：mambo_agents.middleware.mcp 连带加载 mcp 客户端栈等重依赖
    try:
        from mambo_agents.middleware.mcp import mcp_tool_name
        return mcp_tool_name(server_name, tool_name)
    except ImportError:  # 运行时环境缺少 mambo_agents 时退化实现（与 mcp_tool_name 同规则）
        import re as _re
        _TOOL_NAME_SAFE_RE = _re.compile(r"[^a-zA-Z0-9_-]")
        return f"{server_name}__{_TOOL_NAME_SAFE_RE.sub('_', tool_name)}"

router = APIRouter()


# ─────────────────── 任务循环「我的规则」工具建议常量 ───────────────────
# 内置 / Backend 工具的参数名建议表，与 mambo_agents 执行侧工具定义对齐。
# 剔除 goal 相关工具（get_goal / create_goal / update_goal，由中间件注入，不可作为完成条件）。
_BUILTIN_TOOL_ARGS: Dict[str, List[str]] = {
    "ls": ["path"],
    "read": ["file_path", "offset", "limit", "include_line_numbers"],
    "write": ["file_path", "content", "overwrite"],
    "edit": ["file_path", "old_str", "new_str", "replace_all"],
    "grep": ["pattern", "path", "glob", "regex", "offset", "limit"],
    "glob": ["pattern", "path"],
    "copy": ["source", "destination"],
    "tree": ["path", "depth"],
    "delete": ["path"],
    "execute": ["command"],
    "ls_version": ["path"],
    "task": ["description", "subagent_type"],
    "async_task": ["description", "subagent_type"],
    "async_status": ["task_id"],
    "write_plans": ["plans"],
    "show": ["path", "mode", "wait_timeout"],
}

# 无条件存在的内置中间件工具（核心六件 + 子代理 + 计划 + show 视配置）
_BUILTIN_CORE_TOOLS: List[str] = ["ls", "read", "write", "edit", "glob", "grep"]
_BUILTIN_SUBAGENT_TOOLS: List[str] = ["task", "async_task", "async_status"]
_BUILTIN_PLANNING_TOOLS: List[str] = ["write_plans"]
_BUILTIN_SHOW_TOOLS: List[str] = ["show"]


def _extract_tool_args(input_schema: Optional[Dict[str, Any]]) -> List[str]:
    """从 MCP 工具 input_schema（JSON Schema）提取参数名列表。"""
    if not input_schema or not isinstance(input_schema, dict):
        return []
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return [str(k) for k in properties.keys()]


def _append_tool(tools: List[schemas.GoalLoopToolInfo], seen: set, name: str, source: str, args: List[str]):
    """去重追加一个工具建议项。"""
    if name in seen:
        return
    tools.append(schemas.GoalLoopToolInfo(name=name, source=source, args=list(args)))
    seen.add(name)


async def _attach_avatar_url(db: AsyncSession, agent: agent_model.Agent) -> schemas.AgentResponse:
    """辅助函数：将单个 ORM 模型转换为 Schema，并动态挂载头像 URL"""
    agent_resp = schemas.AgentResponse.model_validate(agent)
    if agent.agentAvatarId:
        file_service = FileService(db)
        file_record = await file_service.get_file(agent.agentAvatarId)
        if file_record:
            agent_resp.agentAvatarUrl = file_service.get_url(file_record.storage_path)
    return agent_resp


async def _attach_avatar_urls(db: AsyncSession, agents: List[agent_model.Agent]) -> List[schemas.AgentResponse]:
    """辅助函数：批量将 ORM 模型转换为 Schema，并动态挂载头像 URL（解决 N+1 查询问题）"""
    if not agents:
        return []

    agent_resps = [schemas.AgentResponse.model_validate(a) for a in agents]
    avatar_ids = [a.agentAvatarId for a in agents if a.agentAvatarId]

    if avatar_ids:
        files = await file_crud.get_files_by_ids(db, avatar_ids)
        file_service = FileService(db)
        url_map = {f.id: file_service.get_url(f.storage_path) for f in files}

        for resp in agent_resps:
            if resp.agentAvatarId and resp.agentAvatarId in url_map:
                resp.agentAvatarUrl = url_map[resp.agentAvatarId]

    return agent_resps


async def _validate_avatar_file(file: UploadFile):
    """辅助函数：用于校验上传的头像文件类型和大小"""
    ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types are: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024:.0f} MB."
        )


@router.post(
    "/agents/",
    response_model=schemas.AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新 Agent 或文件夹"
)
async def create_agent(agent: schemas.AgentCreate, db: AsyncSession = Depends(get_db)):
    if agent.resourcePromptList is not None:
        await validate_mounted_resources(db, agent.resourcePromptList)
    try:
        db_agent = await agent_crud.create_agent(db=db, agent=agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return await _attach_avatar_url(db, db_agent)


@router.get(
    "/agents/",
    response_model=List[schemas.AgentResponse],
    summary="获取 Agent 和文件夹列表"
)
async def read_agents(skip: int = 0, limit: int = 1000, db: AsyncSession = Depends(get_db)):
    agents = await agent_crud.get_agents(db, skip=skip, limit=limit)
    return await _attach_avatar_urls(db, agents)


@router.get(
    "/agents/children",
    response_model=List[schemas.AgentResponse],
    summary="批量获取子 Agent 和文件夹"
)
async def read_agent_children(
        parentIds: List[str] = Query(..., description="父节点ID列表，'root'代表根目录"),
        db: AsyncSession = Depends(get_db)
):
    agents = await agent_crud.get_agents_by_parent_ids(db, parent_ids=parentIds)
    return await _attach_avatar_urls(db, agents)


@router.get(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="获取单个 Agent 或文件夹的配置"
)
async def read_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _attach_avatar_url(db, db_agent)


@router.put(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="更新 Agent 或文件夹配置"
)
async def update_agent_settings(
        agent_id: str,
        agent_update: schemas.AgentUpdate,
        db: AsyncSession = Depends(get_db)
):
    if agent_update.resourcePromptList is not None:
        await validate_mounted_resources(db, agent_update.resourcePromptList)

    if agent_update.memoryResourceIds is not None:
        await validate_memory_resources(db, agent_update.memoryResourceIds)
        # 合并 memory_resource_ids 到 agentParameters（enable_memory 由前端控制）
        base = agent_update.agentParameters or schemas.MamboAgentParametersSchema()
        agent_update.agentParameters = base.model_copy(update={"memory_resource_ids": agent_update.memoryResourceIds})

    if agent_update.securityReviewConfig is not None:
        base = agent_update.agentParameters or schemas.MamboAgentParametersSchema()
        agent_update.agentParameters = base.model_copy(update={"security_review": agent_update.securityReviewConfig})

    if agent_update.multimodalDescriberConfig is not None:
        base = agent_update.agentParameters or schemas.MamboAgentParametersSchema()
        agent_update.agentParameters = base.model_copy(update={"multimodal_describer": agent_update.multimodalDescriberConfig})

    try:
        updated_agent = await agent_crud.update_agent(db, agent_id=agent_id, agent_update=agent_update)
        if updated_agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return await _attach_avatar_url(db, updated_agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/agents/{agent_id}",
    response_model=schemas.AgentResponse,
    summary="删除 Agent 或文件夹"
)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    db_agent = await agent_crud.delete_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    # 删除时返回最后的状态，同样附带 URL
    return await _attach_avatar_url(db, db_agent)


@router.post(
    "/agents/move",
    status_code=status.HTTP_200_OK,
    summary="移动 Agent 或文件夹"
)
async def move_agents(move_request: schemas.AgentMoveRequest, db: AsyncSession = Depends(get_db)):
    try:
        success = await agent_crud.move_agents(db, move_request=move_request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=400, detail="Move operation failed")
    return {"message": "Move successful"}


@router.get(
    "/agents/{agent_id}/hitl-tools",
    response_model=List[schemas.HitlToolInfo],
    summary="获取 Agent 的可 AI 审核工具列表"
)
async def get_agent_hitl_tools(agent_id: str, db: AsyncSession = Depends(get_db)):
    """返回当前 agent 已纳入 HITL（可被 AI 安全审核）的工具名列表。

    工具来源包括：
    - MCP 工具中 review_mode 为 require_review 的
    - 默认 Backend 中 execute 工具开启了 require_review 的

    前端「审核范围」选择器应基于此列表展示可选项。
    """
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    tools: List[schemas.HitlToolInfo] = []
    seen: set[str] = set()

    # 来源1: MCP 工具中 review_mode == REQUIRE_REVIEW 的
    mcp_ids = db_agent.enabledMcpIds or []
    if mcp_ids:
        mcp_tools = await mcp_crud.get_tools_by_server_ids(db, mcp_ids)
        for tool in mcp_tools:
            if tool.review_mode == ToolReviewMode.REQUIRE_REVIEW.value and tool.name not in seen:
                tools.append(schemas.HitlToolInfo(name=tool.name, source="mcp"))
                seen.add(tool.name)

    # 来源2: 默认 Backend 的 execute.require_review
    # 当 defaultBackendId 未显式设置时，builder 会回退到 backendIds 第一个，
    # 因此这里也必须做同样的回退。
    if db_agent.backendIds:
        effective_default_id: str = db_agent.defaultBackendId or db_agent.backendIds[0]
        backends_db = await backend_crud.get_backends_by_ids(db, db_agent.backendIds)
        for b in backends_db:
            if b.id == effective_default_id and b.tools_config:
                exec_cfg = b.tools_config.get("execute", {})
                if exec_cfg.get("enabled") and exec_cfg.get("require_review"):
                    if "execute" not in seen:
                        tools.append(schemas.HitlToolInfo(name="execute", source="backend"))
                        seen.add("execute")
                    break

    return tools


@router.get(
    "/agents/{agent_id}/goal-loop-tools",
    response_model=List[schemas.GoalLoopToolInfo],
    summary="获取 Agent 任务循环「我的规则」的工具及参数名建议列表"
)
async def get_agent_goal_loop_tools(agent_id: str, db: AsyncSession = Depends(get_db)):
    """返回当前 agent 任务循环「我的规则」可选的工具名与参数名建议。

    工具名与执行侧（mambo_agents goal_loop 的 tool_called_at_least）保持一致：
    - MCP 工具：``服务器名__工具名``（与 mcp_tool_name 规则一致），参数名取自 input_schema
    - Backend 工具：execute / tree / delete / copy / ls_version
    - 内置中间件工具：ls/read/write/edit/glob/grep/task/async_task/async_status/write_plans/show

    goal 相关工具（get_goal / create_goal / update_goal）由中间件注入，不纳入建议。
    前端「我的规则」完成条件选择器应基于此列表展示可选项。
    """
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    tools: List[schemas.GoalLoopToolInfo] = []
    seen: set[str] = set()

    # 来源1: 启用的 MCP 工具（is_enabled）→ 服务器名__工具名 + input_schema 参数名
    mcp_ids = db_agent.enabledMcpIds or []
    if mcp_ids:
        servers = await mcp_crud.get_mcp_servers_by_ids(db, mcp_ids)
        enabled_servers = {s.id: s.name for s in servers if s.isEnabled}
        if enabled_servers:
            mcp_tools = await mcp_crud.get_tools_by_server_ids(db, mcp_ids)
            for tool in mcp_tools:
                sname = enabled_servers.get(tool.server_id)
                if not sname:
                    continue
                _append_tool(
                    tools, seen,
                    name=_mcp_tool_name(sname, tool.name),
                    source="mcp",
                    args=_extract_tool_args(tool.input_schema),
                )

    # 来源2: Backend 工具（默认 backend 决定 execute 可用性；RESOURCE 附加 ls_version）
    # 与 hitl-tools 相同的回退规则：defaultBackendId 未设置时取 backendIds 第一个
    if db_agent.backendIds:
        effective_default_id: str = db_agent.defaultBackendId or db_agent.backendIds[0]
        backends_db = await backend_crud.get_backends_by_ids(db, db_agent.backendIds)
        for b in backends_db:
            if b.id != effective_default_id:
                continue
            # execute 仅当默认 backend 开启时注册（Local/SSH/API）
            exec_cfg = (b.tools_config or {}).get("execute", {})
            if exec_cfg.get("enabled"):
                _append_tool(tools, seen, name="execute", source="backend",
                             args=_BUILTIN_TOOL_ARGS.get("execute", []))
            # tree / delete：所有 Backend 类型固定提供
            _append_tool(tools, seen, name="tree", source="backend",
                         args=_BUILTIN_TOOL_ARGS.get("tree", []))
            _append_tool(tools, seen, name="delete", source="backend",
                         args=_BUILTIN_TOOL_ARGS.get("delete", []))
            # copy：HybridWorkspaceBackend 包装层固定提供
            _append_tool(tools, seen, name="copy", source="backend",
                         args=_BUILTIN_TOOL_ARGS.get("copy", []))
            # ls_version：RESOURCE 类型 backend（MamboResourceBackend）专属
            if b.backendType == BackendType.RESOURCE.value:
                _append_tool(tools, seen, name="ls_version", source="backend",
                             args=_BUILTIN_TOOL_ARGS.get("ls_version", []))
            break

    # 来源3: 内置中间件工具（固定存在；show 跟随 enable_show 配置）
    agent_params = db_agent.agentParameters or {}
    builtin_names: List[str] = list(_BUILTIN_CORE_TOOLS)
    builtin_names += list(_BUILTIN_SUBAGENT_TOOLS)
    builtin_names += list(_BUILTIN_PLANNING_TOOLS)
    if agent_params.get("enable_show", True):
        builtin_names += list(_BUILTIN_SHOW_TOOLS)
    for name in builtin_names:
        _append_tool(tools, seen, name=name, source="builtin",
                     args=_BUILTIN_TOOL_ARGS.get(name, []))

    return tools


@router.put(
    "/agents/{agent_id}/avatar",
    response_model=schemas.File,
    summary="上传 Agent 头像"
)
async def upload_agent_avatar(
        agent_id: str,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db)
):
    await _validate_avatar_file(file)

    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_avatar_id = db_agent.agentAvatarId

    file_service = FileService(db)

    # 1. 保存新头像文件
    new_file_record = await file_service.save_file(
        file=file,
        management_type=[FileManagementType.AGENT_AVATAR.value],
        sub_path="avatars"
    )

    # 2. 更新 Agent 的 agentAvatarId
    await agent_crud.update_agent(
        db,
        agent_id=agent_id,
        agent_update=schemas.AgentUpdate(agentAvatarId=new_file_record.id)
    )

    # 3. 删除旧头像文件防止存储堆积
    if old_avatar_id:
        await file_service.delete_file(old_avatar_id)

    return file_service.convert_to_schema(new_file_record)


@router.post(
    "/agents/{agent_id}/duplicate",
    response_model=schemas.AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="复制 Agent（副本）"
)
async def duplicate_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """基于现有 Agent 创建一个副本，名称自动添加 ' - 副本' 后缀"""
    import re

    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if db_agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 解析原名称的基准名（去掉已有的 "-副本" 或 "-副本N" 后缀）
    base_name = db_agent.name
    match = re.match(r'^(.*?)(?:-副本(?:\d+)?)?$', base_name)
    if match:
        base_name = match.group(1).strip()

    # 查找已有副本编号，生成新名称
    all_agents = await agent_crud.get_agents(db, skip=0, limit=10000)
    existing_nums: list = []
    pattern = re.compile(r'^' + re.escape(base_name) + r'-副本(\d+)?$')
    for a in all_agents:
        m = pattern.match(a.name)
        if m:
            num = int(m.group(1)) if m.group(1) else 1
            existing_nums.append(num)

    if not existing_nums:
        new_name = f"{base_name}-副本"
    else:
        next_num = max(existing_nums) + 1
        new_name = f"{base_name}-副本{next_num}"

    # 构造副本 Agent（完整复制，含头像）
    new_agent = schemas.AgentCreate(
        name=new_name,
        parentId=db_agent.parentId,
        itemType=db_agent.itemType,
        AgentType=db_agent.AgentType,
        systemPrompt=db_agent.systemPrompt,
        description=db_agent.description,
        modelParameters=db_agent.modelParameters,
        agentParameters=db_agent.agentParameters,
        aiModelId=db_agent.aiModelId,
        agentAvatarId=db_agent.agentAvatarId,
        resourcePromptList=db_agent.resourcePromptList or [],
        enabledMcpIds=db_agent.enabledMcpIds or [],
        subAgents=db_agent.subAgents or [],
        backendIds=db_agent.backendIds or [],
        defaultBackendId=db_agent.defaultBackendId,
    )

    db_new = await agent_crud.create_agent(db=db, agent=new_agent)
    return await _attach_avatar_url(db, db_new)


@router.delete(
    "/agents/{agent_id}/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Agent 头像"
)
async def delete_agent_avatar(
        agent_id: str,
        db: AsyncSession = Depends(get_db)
):
    db_agent = await agent_crud.get_agent(db, agent_id=agent_id)
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_avatar_id = db_agent.agentAvatarId
    if not old_avatar_id:
        return None

    file_service = FileService(db)

    # 1. 删除头像文件
    await file_service.delete_file(old_avatar_id)

    # 2. 将 Agent 的 agentAvatarId 设为空
    await agent_crud.update_agent(
        db,
        agent_id=agent_id,
        agent_update=schemas.AgentUpdate(agentAvatarId=None)
    )

    return None
