"""mambo agent — Agent 管理（树形目录: 文件夹/Agent 创建与配置）。"""
from __future__ import annotations

import argparse
import json
import os
import sys

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import (
    agent_type_label,
    build_resource_tree,
    resolve_agent,
    resolve_agent_parent,
    resolve_backend,
    resolve_mcp_server,
    resolve_model,
    resolve_resource,
    resource_path_of,
)
from backend.mambo_cli.util import UsageError, parse_bool
from backend.mambo_cli.llm_params import build_definition_map, format_limit, suggested_params, validate_param

AGENT_TYPES = ["Mambo", "ReActAgent"]

# 表格列 formatter 用（接收单元格值，非 dict）
AGENT_TYPE_LABELS = {
    "folder": "[folder]",
    "agent": "[agent]",
}

# agentParameters 布尔平铺参数: flag -> (argparse dest, 字段名)
_BOOL_AGENT_PARAMS = [
    ("--planning", "planning", "enable_planning"),
    ("--memory", "memory", "enable_memory"),
    ("--summarization", "summarization", "enable_summarization"),
    ("--show", "show", "enable_show"),
    ("--general-purpose", "general_purpose", "include_general_purpose"),
]

# summarization_config 平铺参数: flag -> (字段, choices)
_SUMMARY_PARAMS = [
    ("--summary-trigger-type", "trigger_type", ["fraction", "tokens", "messages"]),
    ("--summary-trigger-value", "trigger_value", None),
    ("--summary-keep-type", "keep_type", ["fraction", "tokens", "messages"]),
    ("--summary-keep-value", "keep_value", None),
    ("--summary-offload", "offload_to_backend", None),
]


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "agent", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="Agent 管理（树形目录: 文件夹/Agent 创建与配置）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="agent_action", metavar="<action>")

    def cmd(name, help_text, advanced=False):
        if advanced:
            help_text = "[高级] " + help_text
        cp = sp.add_parser(
            name, parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
            help=help_text,
        )
        add_leveled_help(cp)
        if advanced:
            mark_advanced(cp)
        return cp

    lp = cmd("list", "列出 Agent 与文件夹（可按目录过滤/树状展示）")
    lp.add_argument("--tree", action="store_true", help="树状展示层级")
    lp.add_argument("--path", metavar="DIR", help="只显示该目录子树（目录路径/名称/短ID）")
    lp.set_defaults(func=cmd_list)

    sp_cmd = cmd("show", "查看 Agent 配置详情")
    sp_cmd.add_argument("agent", help="Agent 引用（/父/名称 路径/唯一名称/短ID）")
    sp_cmd.set_defaults(func=cmd_show)

    mk = cmd("mkdir", "创建文件夹节点")
    mk.add_argument("path", help="文件夹路径（如 /团队/研发）")
    mk.set_defaults(func=cmd_mkdir)

    cp = cmd("create", "创建 Agent")
    cp.add_argument("path", help="Agent 路径（末段为名称，如 /团队/数据分析师）")
    cp.add_argument("--type", dest="agent_type", choices=AGENT_TYPES, default="Mambo",
                    help="Agent 类型（默认 Mambo，可选 ReActAgent）")
    cp.add_argument("--description", help="描述")
    cp.add_argument("--model", metavar="M", help="绑定模型（模型引用，如 openai:gpt-4o）")
    _add_system_prompt_args(cp, allow_clear=False)
    _add_agent_parameter_args(cp)
    cp.set_defaults(func=cmd_create)

    up = cmd("update", "修改 Agent 配置（只更新传入的参数）")
    up.add_argument("agent", help="Agent 引用")
    up.add_argument("--name", help="新名称")
    up.add_argument("--description", help="描述")
    up.add_argument("--type", dest="agent_type", choices=AGENT_TYPES, help="Agent 类型")
    up.add_argument("--model", metavar="M", help="绑定模型（模型引用）")
    up.add_argument("--default-backend", dest="default_backend", metavar="B",
                    help="默认 Backend（Backend 引用；不自动挂载，需先 mount）")
    _add_system_prompt_args(up, allow_clear=True)
    _add_agent_parameter_args(up)
    up.set_defaults(func=cmd_update)

    dp = cmd("delete", "删除 Agent 或文件夹")
    dp.add_argument("agent", help="Agent 引用")
    dp.add_argument("-R", "--recursive", action="store_true", help="递归删除文件夹（必填）")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    mp = cmd("mv", "移动 Agent 或文件夹到目标目录（inside）")
    mp.add_argument("agent", help="Agent 引用")
    mp.add_argument("target", metavar="<目标目录>", help="目标文件夹路径（/ 或 root 表示根目录）")
    mp.set_defaults(func=cmd_move)

    dup = cmd("duplicate", "复制 Agent（名称自动加 -副本 后缀）")
    dup.add_argument("agent", help="Agent 引用")
    dup.set_defaults(func=cmd_duplicate)

    ex = cmd("export", "导出 Agent 为 .mamboagent 包（含子 Agent/挂载依赖）")
    ex.add_argument("agent", help="Agent 引用（仅 Agent，不支持文件夹）")
    ex.add_argument("--output", metavar="PATH", help="输出路径（目录或文件；缺省当前目录）")
    ex.set_defaults(func=cmd_export)

    imp = cmd("import", "导入 .mamboagent 包（同名冲突自动改名，改名需 --yes 确认）")
    imp.add_argument("--file", required=True, metavar="PATH", help="本地 .mamboagent 包路径")
    imp.add_argument("--into", metavar="DIR", help="导入到哪个 Agent 文件夹（缺省根目录）")
    imp.add_argument("--preview", action="store_true", help="仅预检（dry-run），不写入任何数据")
    imp.add_argument("--name-override", dest="name_overrides", action="append", metavar="K=V",
                     help="覆盖自动改名结果（sourceId=新名称，如 a1b2c3=我的Agent），可重复")
    imp.add_argument("--yes", action="store_true", help="确认导入（存在改名建议时必填）")
    imp.set_defaults(func=cmd_import)

    ic = cmd("import-cleanup", "清理一次导入会话创建的实体（导入失败后回滚用）", advanced=True)
    ic.add_argument("session_id", help="导入会话 ID（导入报告返回）")
    ic.add_argument("--yes", action="store_true", help="确认清理（必填，防误删）")
    ic.set_defaults(func=cmd_import_cleanup)

    mo = cmd("mount", "挂载资源/MCP/Backend/记忆资源（增量追加）")
    _add_mount_args(mo)
    mo.set_defaults(func=cmd_mount)

    um = cmd("unmount", "移除资源/MCP/Backend/记忆资源挂载")
    _add_mount_args(um)
    um.set_defaults(func=cmd_unmount)

    sa = cmd("subagent", "管理子 Agent（add/remove）")
    sasp = sa.add_subparsers(dest="subagent_action", metavar="<sub-action>")

    def scmd(name, help_text):
        cp = sasp.add_parser(
            name, parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
            help=help_text,
        )
        add_leveled_help(cp)
        return cp

    sa_add = scmd("add", "添加子 Agent（可多个）")
    sa_add.add_argument("agent", help="Agent 引用")
    sa_add.add_argument("sub_agents", nargs="+", metavar="<子Agent>", help="子 Agent 引用")
    sa_add.set_defaults(func=cmd_subagent)

    sa_rm = scmd("remove", "移除子 Agent（可多个）")
    sa_rm.add_argument("agent", help="Agent 引用")
    sa_rm.add_argument("sub_agents", nargs="+", metavar="<子Agent>", help="子 Agent 引用")
    sa_rm.set_defaults(func=cmd_subagent)

    ht = cmd("hitl-tools", "查看 Agent 可纳入 AI 安全审核的工具列表", advanced=True)
    ht.add_argument("agent", help="Agent 引用")
    ht.set_defaults(func=cmd_hitl_tools)

    pp = cmd("params", "查看 Agent 可配置的模型参数建议（含范围/默认值）", advanced=True)
    pp.add_argument("agent", help="Agent 引用")
    pp.set_defaults(func=cmd_params)

    return p


# ---------------------------------------------------------------------------
# 参数辅助
# ---------------------------------------------------------------------------

def _add_system_prompt_args(parser, allow_clear: bool) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--system-prompt-content", dest="system_prompt_content", metavar="TEXT",
                       help="系统提示词内容（与 --system-prompt-filepath 互斥）")
    group.add_argument("--system-prompt-filepath", dest="system_prompt_filepath", metavar="PATH",
                       help="从本地文件读取系统提示词（与 --system-prompt-content 互斥）")
    if allow_clear:
        parser.add_argument("--clear-system-prompt", dest="clear_system_prompt",
                            action="store_true", help="清空系统提示词")


def _read_system_prompt(args) -> str | None:
    """返回 None=未传；str=提示词内容。"""
    if args.system_prompt_content is not None:
        return args.system_prompt_content
    if args.system_prompt_filepath is not None:
        if not os.path.isfile(args.system_prompt_filepath):
            raise UsageError(f"文件不存在: {args.system_prompt_filepath}")
        with open(args.system_prompt_filepath, "r", encoding="utf-8") as f:
            return f.read()
    return None


def _add_agent_parameter_args(parser) -> None:
    for flag, _dest, field in _BOOL_AGENT_PARAMS:
        add_arg(parser, flag, metavar="true|false",
                help=f"agentParameters.{field}（缺省不修改）")
    add_arg(parser, "--mcp-tool-threshold", dest="mcp_tool_threshold", type=int, metavar="N",
            help="agentParameters.mcp_direct_tool_threshold: MCP 工具直接暴露阈值")
    add_arg(parser, "--review-enabled", dest="review_enabled", metavar="true|false",
            help="AI 安全审核: security_review.enabled 是否启用")
    add_arg(parser, "--review-model", dest="review_model", metavar="M",
            help="AI 安全审核: 审核模型（模型引用，解析为 model_id）")
    add_arg(parser, "--review-tools", dest="review_tools", action="append", metavar="T",
            help="AI 安全审核: 审核工具列表 security_review.review_tools（可重复，整体替换）")
    for flag, field, choices in _SUMMARY_PARAMS:
        kwargs = dict(dest=field, metavar=field.upper(),
                      help=f"摘要配置 summarization_config.{field}")
        if choices:
            kwargs["choices"] = choices
        elif field in ("trigger_value", "keep_value"):
            kwargs["type"] = float
        add_arg(parser, flag, advanced=True, **kwargs)
    add_arg(parser, "--param", action="append", metavar="KEY=VALUE", advanced=True,
            help="模型参数 modelParameters（可重复，如 --param temperature=0.7）")


def _add_mount_args(parser) -> None:
    parser.add_argument("agent", help="Agent 引用")
    parser.add_argument("--resource", action="append", metavar="R",
                        help="挂载资源（路径/唯一名称/短ID），可重复")
    parser.add_argument("--mcp", action="append", metavar="S",
                        help="启用 MCP 服务器（唯一名称/短ID），可重复")
    parser.add_argument("--backend", action="append", metavar="B",
                        help="挂载 Backend（唯一名称/短ID），可重复")
    parser.add_argument("--memory-resource", dest="memory_resource", action="append", metavar="R",
                        help="记忆资源（资源引用），可重复")


def _parse_bool_flag(flag: str, value) -> bool:
    try:
        return parse_bool(value)
    except argparse.ArgumentTypeError as exc:
        raise UsageError(f"{flag}: {exc}")


def _build_agent_parameters(args) -> dict:
    """从平铺参数构建 agentParameters 增量（未传的键不出现）。"""
    params = {}
    for flag, dest, field in _BOOL_AGENT_PARAMS:
        value = getattr(args, dest, None)
        if value is not None:
            params[field] = _parse_bool_flag(flag, value)
    if args.mcp_tool_threshold is not None:
        params["mcp_direct_tool_threshold"] = args.mcp_tool_threshold
    summary = {}
    for _flag, field, _choices in _SUMMARY_PARAMS:
        value = getattr(args, field, None)
        if value is not None:
            summary[field] = value
    if summary:
        params["summarization_config"] = summary
    review = {}
    if args.review_enabled is not None:
        review["enabled"] = _parse_bool_flag("--review-enabled", args.review_enabled)
    if args.review_model is not None:
        review["model_id"] = args.review_model  # 占位，由调用方解析为模型 ID
    if args.review_tools is not None:
        review["review_tools"] = args.review_tools
    if review:
        params["security_review"] = review
    return params


def _resolve_review_model(params: dict, args, providers) -> None:
    """将 --review-model 的模型引用解析为 DB ID（覆盖占位值）。"""
    if args.review_model:
        model = resolve_model(providers, args.review_model)
        params.setdefault("security_review", {})["model_id"] = model["id"]


def _build_model_parameters(args, def_map: dict) -> dict:
    """解析 --param KEY=VALUE 列表为 modelParameters 字典（校验 key/类型/范围）。"""
    result = {}
    for item in args.param or []:
        if "=" not in item:
            raise UsageError(f"--param 需要 KEY=VALUE 形式: '{item}'")
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise UsageError(f"--param 的 KEY 不能为空: '{item}'")
        result[key] = validate_param(def_map, key, value)
    return result


def _deep_merge(base: dict, patch: dict) -> dict:
    """深合并字典（嵌套 dict 递归合并，用于 agentParameters 部分更新）。"""
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _ensure_name_available(agents: list[dict], parent_id, name: str) -> None:
    """创建前检查：同父目录下不允许同名（folder/agent 共享同名池子）。"""
    for a in agents:
        if a.get("name") == name and (a.get("parentId") or None) == (parent_id or None):
            raise UsageError(
                f"'{name}' 已存在（同级同名节点 {a['id'][:8]}）。"
                "同一文件夹下名称必须唯一。"
            )


def _model_ref_map(providers: list[dict]) -> dict:
    """模型 ID -> '服务商名:modelId' 可读引用映射。"""
    ref = {}
    for p in providers:
        for m in p.get("models", []):
            ref[m["id"]] = f"{p.get('name')}:{m.get('modelId')}"
    return ref


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

@with_api
def cmd_list(args, api):
    agents = api.list_agents()
    if args.path:
        target = resolve_agent(agents, args.path)
        if target.get("itemType") != "folder":
            raise UsageError(f"'{args.path}' 不是文件夹，无法按目录过滤。")
        children, _roots, by_id = build_resource_tree(agents)
        subtree = []
        def collect(rid):
            subtree.append(by_id[rid])
            for child in children.get(rid, []):
                collect(child["id"])
        collect(target["id"])
        agents = subtree
    if args.json:
        output.print_json(agents)
        return 0
    by_id = {a["id"]: a for a in agents}
    if args.tree:
        # args.path 过滤后 roots 即目标节点，无需额外处理
        children, roots, _by_id = build_resource_tree(agents)
        _print_tree(children, roots, by_id)
        return 0
    rows = [{
        "id": a["id"],
        "path": resource_path_of(a["id"], by_id, agents),
        "itemType": a.get("itemType"),
        "name": a.get("name"),
        "description": a.get("description") or "",
    } for a in agents]
    output.print_table(rows, [
        ("id", "ID", output.short_id),
        ("path", "PATH", None),
        ("itemType", "TYPE", lambda v: AGENT_TYPE_LABELS.get(v, "[agent]")),
        ("name", "NAME", None),
        ("description", "DESCRIPTION", None),
    ])
    return 0


def _print_tree(children, roots, by_id, prefix=""):
    for i, node in enumerate(roots):
        last = i == len(roots) - 1
        branch = "└─ " if last else "├─ "
        print(f"{prefix}{branch}{agent_type_label(node)} {node['name']}  ({node['id'][:8]})")
        sub = children.get(node["id"], [])
        if sub:
            _print_tree(children, sub, by_id, prefix + ("   " if last else "│  "))


@with_api
def cmd_show(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if args.json:
        output.print_json(agent)
        return 0
    by_id = {a["id"]: a for a in agents}
    path = resource_path_of(agent["id"], by_id, agents)
    if agent.get("itemType") == "folder":
        print(f"文件夹: {path}")
        output.print_kv(agent, ["id", "name", "itemType", "description"])
        print("（文件夹无 Agent 配置；用 mambo agent list --path 查看子项）")
        return 0
    providers = api.list_providers()
    model_ref = _model_ref_map(providers)
    backends = api.list_backends()
    backend_name = {b["id"]: b["name"] for b in backends}
    resources = api.list_resources()
    res_by_id = {r["id"]: r for r in resources}
    mcp_servers = api.list_mcp_servers()
    mcp_name = {s["id"]: s["name"] for s in mcp_servers}

    def fmt_ids(ids, name_map):
        ids = ids or []
        return ", ".join(name_map.get(i, i[:8]) for i in ids) or "(空)"

    print(f"Agent: {path}")
    output.print_kv(agent, ["id", "name", "itemType", "AgentType", "description"])
    model_id = agent.get("aiModelId")
    print(f"aiModelId: {model_ref.get(model_id, model_id[:8]) if model_id else '(未绑定)'}")
    default_bid = agent.get("defaultBackendId")
    print(f"defaultBackendId: {backend_name.get(default_bid, default_bid[:8]) if default_bid else '(未设置)'}")
    if agent.get("systemPrompt"):
        print(f"systemPrompt: {agent['systemPrompt']}")
    print(f"agentParameters: {json.dumps(agent.get('agentParameters') or {}, ensure_ascii=False)}")
    print(f"resourcePromptList: {fmt_ids(agent.get('resourcePromptList'), {r['id']: resource_path_of(r['id'], res_by_id, resources) for r in resources})}")
    print(f"enabledMcpIds: {fmt_ids(agent.get('enabledMcpIds'), mcp_name)}")
    print(f"backendIds: {fmt_ids(agent.get('backendIds'), backend_name)}")
    print(f"subAgents: {fmt_ids(agent.get('subAgents'), {a['id']: a['name'] for a in agents})}")


@with_api
def cmd_mkdir(args, api):
    agents = api.list_agents()
    parent_id, name = resolve_agent_parent(agents, args.path)
    _ensure_name_available(agents, parent_id, name)
    created = api.create_agent({"name": name, "itemType": "folder", "parentId": parent_id})
    if args.json:
        output.print_json(created)
    else:
        by_id = {a["id"]: a for a in api.list_agents()}
        print(f"已创建文件夹: {resource_path_of(created['id'], by_id, agents)}")
    return 0


@with_api
def cmd_create(args, api):
    agents = api.list_agents()
    parent_id, name = resolve_agent_parent(agents, args.path)
    _ensure_name_available(agents, parent_id, name)
    data = {"name": name, "itemType": "agent", "parentId": parent_id}
    if args.description is not None:
        data["description"] = args.description
    data["AgentType"] = args.agent_type
    providers = api.list_providers()
    if args.model:
        model = resolve_model(providers, args.model)
        data["aiModelId"] = model["id"]
    prompt = _read_system_prompt(args)
    if prompt is not None:
        data["systemPrompt"] = prompt
    params = _build_agent_parameters(args)
    _resolve_review_model(params, args, providers)
    model_params = _build_model_parameters(args, build_definition_map(
        (api.get_system_config().get("llm_parameters") or []) if args.param else []))
    if model_params:
        data["modelParameters"] = model_params
    if params:
        data["agentParameters"] = params
    created = api.create_agent(data)
    if args.json:
        output.print_json(created)
    else:
        by_id = {a["id"]: a for a in api.list_agents()}
        print(f"已创建 Agent: {resource_path_of(created['id'], by_id, agents)}")
    return 0


@with_api
def cmd_update(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，没有 Agent 配置可更新。")
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.description is not None:
        data["description"] = args.description
    if args.agent_type is not None:
        data["AgentType"] = args.agent_type
    providers = api.list_providers()
    if args.model:
        model = resolve_model(providers, args.model)
        data["aiModelId"] = model["id"]
    if args.default_backend:
        backends = api.list_backends()
        backend = resolve_backend(backends, args.default_backend)
        data["defaultBackendId"] = backend["id"]
    if args.clear_system_prompt:
        data["systemPrompt"] = None
    else:
        prompt = _read_system_prompt(args)
        if prompt is not None:
            data["systemPrompt"] = prompt
    params = _build_agent_parameters(args)
    _resolve_review_model(params, args, providers)
    model_params = _build_model_parameters(args, build_definition_map(
        (api.get_system_config().get("llm_parameters") or []) if args.param else []))
    if model_params:
        base = dict(agent.get("modelParameters") or {})
        base.update(model_params)
        data["modelParameters"] = base
    if params:
        base = dict(agent.get("agentParameters") or {})
        data["agentParameters"] = _deep_merge(base, params)
    if not data:
        raise UsageError("至少提供一个要修改的参数（mambo agent update --help 查看）")
    updated = api.update_agent(agent["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        print(f"已更新 Agent: {updated['id']} ({updated['name']})")
    return 0


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") == "folder":
        if not args.recursive:
            raise UsageError(f"'{args.agent}' 是文件夹，递归删除需 -R")
        children, _roots, _by_id = build_resource_tree(agents)

        def count_subtree(rid):
            total = 0
            for child in children.get(rid, []):
                total += 1 + count_subtree(child["id"])
            return total

        n = count_subtree(agent["id"])
        print(f"将递归删除文件夹 '{agent['name']}' 及其 {n} 个子项...", file=sys.stderr)
    api.delete_agent(agent["id"])
    if args.json:
        output.print_json({"deleted": agent["id"]})
    else:
        print(f"已删除: {agent['id']} ({agent['name']})")
    return 0


@with_api
def cmd_move(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if args.target in ("/", "root"):
        reference_id = "root"
    else:
        dest = resolve_agent(agents, args.target)
        if dest.get("itemType") != "folder":
            raise UsageError(f"目标 '{args.target}' 不是文件夹。")
        reference_id = dest["id"]
    api.move_agents([agent["id"]], reference_id, "inside")
    if args.json:
        output.print_json({"moved": agent["id"], "into": reference_id})
    else:
        print(f"已移动: {agent['name']} → {args.target}")
    return 0


@with_api
def cmd_duplicate(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    created = api.duplicate_agent(agent["id"])
    if args.json:
        output.print_json(created)
    else:
        print(f"已复制: {created['id']} ({created['name']})")
    return 0


@with_api
def cmd_export(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，仅 Agent 可导出（含其子 Agent）。")
    content, suggested = api.export_agent(agent["id"])
    filename = suggested or f"{agent['name']}.mamboagent"
    if args.output and os.path.isdir(args.output):
        out_path = os.path.join(args.output, filename)
    else:
        out_path = args.output or filename
    with open(out_path, "wb") as f:
        f.write(content)
    if args.json:
        output.print_json({"exported": agent["id"], "file": out_path, "size": len(content)})
    else:
        print(f"已导出 Agent '{agent['name']}' → {out_path}（{len(content)} 字节）")
    return 0


def _parse_name_overrides(args) -> dict | None:
    if not args.name_overrides:
        return None
    overrides = {}
    for item in args.name_overrides:
        if "=" not in item:
            raise UsageError(f"--name-override 需要 sourceId=新名称 形式: '{item}'")
        key, _, value = item.partition("=")
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise UsageError(f"--name-override 需要 sourceId=新名称 形式: '{item}'")
        overrides[key] = value
    return overrides


def _read_package(pkg_path: str) -> dict:
    """读取 .mamboagent 包（gzip JSON），用于解析包内 sourceId。"""
    import gzip
    try:
        with gzip.open(pkg_path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except Exception as exc:
        raise UsageError(f"不是有效的 .mamboagent 包: {pkg_path}（{exc}）")
    return data


def _resolve_name_overrides(args, pkg: dict) -> dict | None:
    """将 --name-override 的短前缀 sourceId 归一化为包内完整 ID。"""
    raw = _parse_name_overrides(args)
    if not raw:
        return None
    source_ids = [e.get("sourceId") for e in
                  pkg.get("agents", []) + pkg.get("providers", []) + pkg.get("backends", [])]
    source_ids = [s for s in source_ids if s]
    resolved = {}
    for key, value in raw.items():
        if key in source_ids:
            resolved[key] = value
            continue
        matches = [s for s in source_ids if s.startswith(key)]
        if len(matches) == 1:
            resolved[matches[0]] = value
        elif not matches:
            raise UsageError(f"--name-override 的 sourceId '{key}' 在包中未找到"
                             f"（可用 mambo agent import --preview 查看实体 sourceId）")
        else:
            raise UsageError(f"--name-override 的 sourceId '{key}' 匹配到多个实体: "
                             + ", ".join(m[:8] for m in matches) + "。请使用更长前缀。")
    return resolved


def _print_import_preview(preview: dict) -> None:
    print(f"预检结果: {'✅ 可导入' if preview.get('importable') else '❌ 不可导入'}")
    print(f"包格式: v{preview.get('format_version')}（导出端 MamboChat {preview.get('mambochat_version')}，"
          f"导出于 {preview.get('exported_at')}）")
    if preview.get("description"):
        print(f"描述: {preview['description']}")
    for warn in preview.get("warnings") or []:
        print(f"  [警告] {warn}")
    suggestions = preview.get("rename_suggestions") or []
    if suggestions:
        print("改名建议（同名冲突自动改名）:")
        for s in suggestions:
            print(f"  {s.get('entity_type')} '{s.get('original_name')}' → '{s.get('new_name')}'"
                  f"（sourceId: {s.get('source_id')}）")
    missing = preview.get("providers_missing_api_key") or []
    if missing:
        print("以下服务商缺少 API Key，导入后需手动补充:")
        for p in missing:
            print(f"  {p.get('name')}（源 ID {p.get('source_id', '?')[:8]}）")
    tree = preview.get("resource_tree") or []
    if tree:
        print("将导入的资源树:")
        def print_tree(nodes, indent):
            for n in nodes:
                print(f"{indent}{n.get('name')} [{n.get('itemType')}]")
                print_tree(n.get("children") or [], indent + "  ")
        print_tree(tree, "  ")


@with_api
def cmd_import(args, api):
    if not os.path.isfile(args.file):
        raise UsageError(f"文件不存在: {args.file}")
    with open(args.file, "rb") as f:
        data = f.read()

    target_id = None
    if args.into and args.into not in ("/", "root"):
        agents = api.list_agents()
        dest = resolve_agent(agents, args.into)
        if dest.get("itemType") != "folder":
            raise UsageError(f"--into '{args.into}' 不是文件夹。")
        target_id = dest["id"]

    overrides = _resolve_name_overrides(args, _read_package(args.file))
    filename = os.path.basename(args.file)

    if args.preview:
        preview = api.import_agent(data, filename, target_id, overrides, preview=True)
        if args.json:
            output.print_json(preview)
            return 0
        _print_import_preview(preview)
        return 0

    # 正式导入：先预检拿改名建议，有冲突时需 --yes 确认
    preview = api.import_agent(data, filename, target_id, overrides, preview=True)
    suggestions = preview.get("rename_suggestions") or []
    if suggestions and not args.yes:
        lines = [f"  {s.get('entity_type')} '{s.get('original_name')}' → '{s.get('new_name')}'"
                 for s in suggestions]
        raise UsageError(
            "导入将发生同名冲突自动改名:\n" + "\n".join(lines) +
            "\n接受改名请加 --yes（或先 --preview 查看，用 --name-override 指定名称）"
        )

    report = api.import_agent(data, filename, target_id, overrides, preview=False)
    if args.json:
        output.print_json(report)
        return 0 if report.get("success") else 1
    if report.get("success"):
        print(f"✅ 导入成功: 会话 {report.get('import_session_id')}")
        main_id = report.get("main_agent_id")
        if main_id:
            agents = api.list_agents()
            by_id = {a["id"]: a for a in agents}
            print(f"主 Agent: {resource_path_of(main_id, by_id, agents)}")
        for ent in report.get("created") or []:
            print(f"  [{ent.get('entity_type')}] {ent.get('new_id')}（源 {ent.get('source_id', '?')[:8]}）")
        for s in suggestions:
            print(f"  （改名: {s.get('original_name')} → {s.get('new_name')}）")
        missing = report.get("providers_missing_api_key") or []
        if missing:
            print("⚠️ 以下服务商缺少 API Key，需手动补充:")
            for p in missing:
                print(f"  {p.get('name')}")
        return 0
    print(f"❌ 导入失败（阶段 {report.get('failed_phase')}）: {report.get('error')}")
    print(f"已创建的实体可用以下命令清理: mambo agent import-cleanup "
          f"{report.get('import_session_id')} --yes")
    return 1


@with_api
def cmd_import_cleanup(args, api):
    if not args.yes:
        raise UsageError("清理操作需要 --yes 确认（防止误删）")
    report = api.cleanup_import(args.session_id)
    if args.json:
        output.print_json(report)
    else:
        cleaned = report.get("cleaned") or []
        print(f"已清理 {len(cleaned)} 个实体"
              + ("" if not cleaned else ": " + ", ".join(cleaned)))
    return 0


def _resolve_mount_refs(api, refs, kind: str) -> list[str]:
    """批量解析挂载引用为 ID 列表。kind: resource/mcp/backend。"""
    if not refs:
        return []
    if kind == "resource":
        resources = api.list_resources()
        return [resolve_resource(resources, r)["id"] for r in refs]
    if kind == "mcp":
        servers = api.list_mcp_servers()
        return [resolve_mcp_server(servers, s)["id"] for s in refs]
    backends = api.list_backends()
    return [resolve_backend(backends, b)["id"] for b in refs]


@with_api
def cmd_mount(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，不能挂载（仅 Agent 可挂载）。")
    data = {}
    resource_ids = _resolve_mount_refs(api, args.resource, "resource")
    if resource_ids:
        data["resourcePromptList"] = list(dict.fromkeys(
            (agent.get("resourcePromptList") or []) + resource_ids))
    mcp_ids = _resolve_mount_refs(api, args.mcp, "mcp")
    if mcp_ids:
        data["enabledMcpIds"] = list(dict.fromkeys(
            (agent.get("enabledMcpIds") or []) + mcp_ids))
    backend_ids = _resolve_mount_refs(api, args.backend, "backend")
    if backend_ids:
        data["backendIds"] = list(dict.fromkeys(
            (agent.get("backendIds") or []) + backend_ids))
    mem_ids = _resolve_mount_refs(api, args.memory_resource, "resource")
    if mem_ids:
        params = dict(agent.get("agentParameters") or {})
        params["memory_resource_ids"] = list(dict.fromkeys(
            (params.get("memory_resource_ids") or []) + mem_ids))
        data["agentParameters"] = params
    if not data:
        raise UsageError("至少提供一个挂载参数（--resource / --mcp / --backend / --memory-resource）")
    updated = api.update_agent(agent["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        print(f"已挂载到 Agent: {updated['name']}")
    return 0


@with_api
def cmd_unmount(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，没有挂载可移除。")
    data = {}
    resource_ids = _resolve_mount_refs(api, args.resource, "resource")
    if resource_ids:
        data["resourcePromptList"] = [i for i in (agent.get("resourcePromptList") or [])
                                      if i not in resource_ids]
    mcp_ids = _resolve_mount_refs(api, args.mcp, "mcp")
    if mcp_ids:
        data["enabledMcpIds"] = [i for i in (agent.get("enabledMcpIds") or [])
                                 if i not in mcp_ids]
    backend_ids = _resolve_mount_refs(api, args.backend, "backend")
    if backend_ids:
        data["backendIds"] = [i for i in (agent.get("backendIds") or [])
                              if i not in backend_ids]
    mem_ids = _resolve_mount_refs(api, args.memory_resource, "resource")
    if mem_ids:
        params = dict(agent.get("agentParameters") or {})
        params["memory_resource_ids"] = [i for i in (params.get("memory_resource_ids") or [])
                                         if i not in mem_ids]
        data["agentParameters"] = params
    if not data:
        raise UsageError("至少提供一个要移除的挂载参数（--resource / --mcp / --backend / --memory-resource）")
    updated = api.update_agent(agent["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        print(f"已从 Agent 移除挂载: {updated['name']}")
    return 0


@with_api
def cmd_subagent(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，不能挂载子 Agent。")
    existing = agent.get("subAgents") or []
    refs = args.sub_agents
    if args.subagent_action == "add":
        new_ids = []
        for ref in refs:
            target = resolve_agent(agents, ref)
            if target.get("itemType") != "agent":
                raise UsageError(f"子 Agent '{target['name']}' 是文件夹，不能作为子 Agent。")
            new_ids.append(target["id"])
        merged = list(dict.fromkeys(existing + new_ids))
        updated = api.update_agent(agent["id"], {"subAgents": merged})
        if args.json:
            output.print_json(updated)
        else:
            print(f"已添加 {len(new_ids)} 个子 Agent: {updated['name']}（共 {len(merged)} 个）")
    else:  # remove
        rem_ids = []
        for ref in refs:
            target = resolve_agent(agents, ref)
            rem_ids.append(target["id"])
        remaining = [i for i in existing if i not in rem_ids]
        updated = api.update_agent(agent["id"], {"subAgents": remaining})
        if args.json:
            output.print_json(updated)
        else:
            print(f"已移除 {len(rem_ids)} 个子 Agent: {updated['name']}（剩余 {len(remaining)} 个）")
    return 0


@with_api
def cmd_hitl_tools(args, api):
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    tools = api.get_agent_hitl_tools(agent["id"])
    if args.json:
        output.print_json(tools)
        return 0
    output.print_table(tools, [
        ("name", "NAME", None),
        ("source", "SOURCE", None),
    ])
    return 0


@with_api
def cmd_params(args, api):
    """显示建议模型参数（前端 dynamicParameters 同款过滤逻辑）。"""
    agents = api.list_agents()
    agent = resolve_agent(agents, args.agent)
    if agent.get("itemType") != "agent":
        raise UsageError(f"'{args.agent}' 是文件夹，没有模型参数可配置。")
    definitions = api.get_system_config().get("llm_parameters") or []
    supported = set()
    model_label = "(未绑定)"
    model_id = agent.get("aiModelId")
    if model_id:
        providers = api.list_providers()
        model_ref = _model_ref_map(providers)
        model_label = model_ref.get(model_id, model_id[:8])
        for p in providers:
            for m in p.get("models", []):
                if m["id"] == model_id:
                    supported = set((m.get("meta_config") or {}).get("supported_parameters") or [])
                    break
            else:
                continue
            break
    current = agent.get("modelParameters") or {}
    rows = []
    for d in suggested_params(definitions, supported):
        key = d.get("key")
        rows.append({
            "key": key,
            "label": d.get("label"),
            "type": d.get("type"),
            "limit": format_limit(d.get("limit")),
            "default": d.get("default_value"),
            "current": current.get(key, "-"),
        })
    if args.json:
        output.print_json(rows)
        return 0
    print(f"建议参数（模型: {model_label}）:")
    output.print_table(rows, [
        ("key", "KEY", None),
        ("label", "LABEL", None),
        ("type", "TYPE", None),
        ("limit", "LIMIT", None),
        ("default", "DEFAULT", None),
        ("current", "CURRENT", None),
    ])
    return 0
