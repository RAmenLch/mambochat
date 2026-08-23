"""mambo backend — Backend 管理（SSH/API/Resource/Local 文件后端）。"""
from __future__ import annotations

import argparse
import sys

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import resolve_backend, resolve_resource
from backend.mambo_cli.util import UsageError, parse_bool
from backend.utils.path_safe import validate_path_safe_name

BACKEND_TYPES = ["ssh", "api", "resource", "local"]
REVIEW_MODES = ["none", "require_review"]
PASSWORD_MASK = "********"

_BACKEND_KV_KEYS = ["id", "name", "backendType", "description", "configData", "tools_config",
                    "createdAt", "updatedAt"]


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "backend", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="Backend 管理（SSH/API/Resource/Local 文件后端）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="backend_action", metavar="<action>")

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

    lp = cmd("list", "列出全部 Backend")
    lp.add_argument("--type", dest="backend_type", choices=BACKEND_TYPES, help="只显示指定类型")
    lp.set_defaults(func=cmd_list)

    sp_cmd = cmd("show", "查看 Backend 详情（密码/API Key 已脱敏）")
    sp_cmd.add_argument("backend", help="Backend 引用（唯一名称/ID前缀）")
    sp_cmd.set_defaults(func=cmd_show)

    ap = cmd("add", "创建 Backend")
    ap.add_argument("--name", required=True,
                    help="名称（唯一，禁止 / \\ 控制字符与系统保留字）")
    ap.add_argument("--type", dest="backend_type", required=True, choices=BACKEND_TYPES,
                    help=f"类型: {'/'.join(BACKEND_TYPES)}")
    ap.add_argument("--description", help="描述")
    _add_config_args(ap)
    _add_tools_args(ap)
    ap.set_defaults(func=cmd_add)

    up = cmd("update", "修改 Backend（只更新传入的参数；列表传 \"\" 清空）")
    up.add_argument("backend", help="Backend 引用")
    up.add_argument("--name", help="新名称")
    up.add_argument("--description", help="描述")
    _add_config_args(up)
    _add_tools_args(up)
    up.set_defaults(func=cmd_update)

    dp = cmd("delete", "删除 Backend")
    dp.add_argument("backend", help="Backend 引用")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    dup = cmd("duplicate", "复制 Backend（名称自动加 -副本 后缀）")
    dup.add_argument("backend", help="Backend 引用")
    dup.set_defaults(func=cmd_duplicate)

    tp = cmd("test", "测试 Backend 连接（ssh=真实连接; local=目录校验; resource=资源校验; api=不支持）")
    tp.add_argument("backend", help="Backend 引用")
    tp.set_defaults(func=cmd_test)

    sk = cmd("ssh-key", "显示系统全局 SSH 公钥（用于配置免密登录）")
    sk.set_defaults(func=cmd_ssh_key)

    ts = cmd("tool", "管理 Backend 工具配置（set）", advanced=True)
    tsp = ts.add_subparsers(dest="backend_tool_action", metavar="<tool-action>")

    tset = tsp.add_parser(
        "set", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="设置工具启停与审核模式（写入 tools_config）",
    )
    add_leveled_help(tset)
    tset.add_argument("backend", help="Backend 引用")
    tset.add_argument("tool_name", metavar="<工具名>", help="工具名（如 execute）")
    tset.add_argument("--enabled", metavar="true|false", help="是否启用")
    tset.add_argument("--review-mode", dest="review_mode", choices=REVIEW_MODES,
                      help="审核模式（require_review=需要 HITL 审核）")
    tset.set_defaults(func=cmd_tool_set)

    return p


# ---------------------------------------------------------------------------
# 参数辅助
# ---------------------------------------------------------------------------

def _add_config_args(parser) -> None:
    """各类型 configData 参数（add/update 共用）。"""
    parser.add_argument("--edit-whitelist", dest="edit_whitelist", metavar="A,B",
                        help="允许编辑的虚拟路径前缀（逗号分隔；update 传 \"\" 清空）")
    parser.add_argument("--edit-blacklist", dest="edit_blacklist", metavar="A,B",
                        help="禁止编辑的虚拟路径前缀（逗号分隔；update 传 \"\" 清空；与白名单互斥）")
    parser.add_argument("--ignore-dirs", dest="ignore_dirs", metavar="A,B",
                        help="遍历时忽略的目录（逗号分隔；update 传 \"\" 清空）")
    parser.add_argument("--hostname", help="ssh: 远程主机 IP/域名")
    parser.add_argument("--port", type=int, help="ssh: 端口（默认 22）")
    parser.add_argument("--username", help="ssh: 登录用户名")
    parser.add_argument("--password",
                        help="ssh: 密码（缺省用系统密钥免密；update 传 \"********\" 保持原密码，传 \"\" 清空为免密）")
    parser.add_argument("--root-dir", dest="root_dir", metavar="DIR",
                        help="ssh/local: 挂载根目录（ssh 默认 /，local 默认 ~）")
    parser.add_argument("--api-key", dest="api_key", metavar="KEY",
                        help="api: API 密钥（update 传 \"********\" 保持，传 \"\" 清空）")
    parser.add_argument("--resource", metavar="R", help="resource: 挂载的资源文件夹（资源引用）")


def _add_tools_args(parser) -> None:
    parser.add_argument("--execute-enabled", dest="execute_enabled", metavar="true|false",
                        help="工具配置: execute 是否启用")
    parser.add_argument("--execute-review", dest="execute_review", metavar="true|false",
                        help="工具配置: execute 是否需 HITL 审核（require_review）")


def _parse_list(text: str) -> list[str]:
    """解析逗号分隔列表；空字符串表示清空。"""
    if text == "":
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _parse_bool_flag(flag: str, value) -> bool:
    try:
        return parse_bool(value)
    except argparse.ArgumentTypeError as exc:
        raise UsageError(f"{flag}: {exc}")


def _validate_create(args, backend_type: str) -> None:
    if backend_type == "ssh":
        if not args.hostname:
            raise UsageError("ssh 类型需要 --hostname")
        if not args.username:
            raise UsageError("ssh 类型需要 --username")
    elif backend_type == "api":
        if not args.api_key:
            raise UsageError("api 类型需要 --api-key")
    elif backend_type == "resource":
        if not args.resource:
            raise UsageError("resource 类型需要 --resource")


def _build_config_data(args, backend_type: str, existing: dict | None) -> dict:
    """构建 configData。existing 为现有配置（update 时用于部分更新基底）。"""
    data = dict(existing or {})
    if args.edit_whitelist is not None:
        data["edit_whitelist"] = _parse_list(args.edit_whitelist)
    if args.edit_blacklist is not None:
        data["edit_blacklist"] = _parse_list(args.edit_blacklist)
    if args.ignore_dirs is not None:
        data["ignore_dirs"] = _parse_list(args.ignore_dirs)
    if backend_type == "ssh":
        if args.hostname is not None:
            data["hostname"] = args.hostname
        if args.port is not None:
            data["port"] = args.port
        if args.username is not None:
            data["username"] = args.username
        if args.password is not None:
            # 掩码/空串原样传递，由后端 _merge_password 处理（保持/清空/新值）
            data["password"] = args.password
        if args.root_dir is not None:
            data["root_dir"] = args.root_dir
    elif backend_type == "api":
        if args.api_key is not None:
            data["api_key"] = args.api_key
    elif backend_type == "resource":
        if args.resource is not None:
            data["resource_id"] = args.resource  # 调用方解析为 ID
    elif backend_type == "local":
        if args.root_dir is not None:
            data["root_dir"] = args.root_dir
    return data


def _build_tools_config(args, existing: dict | None) -> dict | None:
    """构建 tools_config 增量。返回 None 表示未传任何工具参数。"""
    result = dict(existing or {})
    execute = dict(result.get("execute") or {})
    changed = False
    if args.execute_enabled is not None:
        execute["enabled"] = _parse_bool_flag("--execute-enabled", args.execute_enabled)
        changed = True
    if args.execute_review is not None:
        execute["require_review"] = _parse_bool_flag("--execute-review", args.execute_review)
        changed = True
    if changed:
        result["execute"] = execute
        return result
    return None


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

@with_api
def cmd_list(args, api):
    backends = api.list_backends()
    if args.backend_type:
        backends = [b for b in backends if b.get("backendType") == args.backend_type]
    if args.json:
        output.print_json(backends)
        return 0
    output.print_table(backends, [
        ("id", "ID", output.short_id),
        ("name", "NAME", None),
        ("backendType", "TYPE", None),
        ("description", "DESCRIPTION", None),
    ])
    return 0


@with_api
def cmd_show(args, api):
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    if args.json:
        output.print_json(backend)
        return 0
    output.print_kv(backend, _BACKEND_KV_KEYS, label="Backend:")
    return 0


@with_api
def cmd_add(args, api):
    backend_type = args.backend_type
    _validate_create(args, backend_type)
    # 本地预检：名称规则（与后端 validate_path_safe_name 一致）与唯一性，避免透传英文 400
    try:
        validate_path_safe_name(args.name, label="Backend name")
    except ValueError as exc:
        raise UsageError(f"{exc}")
    backends = api.list_backends()
    if any(b.get("name") == args.name for b in backends):
        raise UsageError(f"Backend 名称 '{args.name}' 已存在（可用 mambo backend show {args.name} 查看）。")
    config = _build_config_data(args, backend_type, None)
    if backend_type == "resource":
        resources = api.list_resources()
        target = resolve_resource(resources, args.resource)
        config["resource_id"] = target["id"]
    data = {"name": args.name, "backendType": backend_type, "configData": config}
    if args.description is not None:
        data["description"] = args.description
    tools = _build_tools_config(args, None)
    if tools:
        data["tools_config"] = tools
    created = api.create_backend(data)
    if args.json:
        output.print_json(created)
    else:
        output.print_kv(created, ["id", "name", "backendType"], label="已创建 Backend:")
    return 0


@with_api
def cmd_update(args, api):
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    backend_type = backend.get("backendType")
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.description is not None:
        data["description"] = args.description
    existing_config = dict(backend.get("configData") or {})
    config = _build_config_data(args, backend_type, existing_config)
    if backend_type == "resource" and args.resource is not None:
        resources = api.list_resources()
        target = resolve_resource(resources, args.resource)
        config["resource_id"] = target["id"]
    if config != existing_config:
        data["configData"] = config
    tools = _build_tools_config(args, backend.get("tools_config"))
    if tools:
        data["tools_config"] = tools
    if not data:
        raise UsageError("至少提供一个要修改的参数（mambo backend update --help 查看）")
    updated = api.update_backend(backend["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        print(f"已更新 Backend: {updated['id']} ({updated['name']})")
    return 0


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    api.delete_backend(backend["id"])
    if args.json:
        output.print_json({"deleted": backend["id"]})
    else:
        print(f"已删除 Backend: {backend['id']} ({backend['name']})")
    return 0


@with_api
def cmd_duplicate(args, api):
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    created = api.duplicate_backend(backend["id"])
    if args.json:
        output.print_json(created)
    else:
        print(f"已复制: {created['id']} ({created['name']})")
    return 0


@with_api
def cmd_test(args, api):
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    backend_type = backend.get("backendType")
    if backend_type == "ssh":
        result = api.test_ssh_backend(backend.get("configData") or {}, backend["id"])
        ok = bool(result.get("success"))
        message = result.get("message") or ""
    elif backend_type == "local":
        root_dir = (backend.get("configData") or {}).get("root_dir") or "~"
        result = api.ls_backend_dir("local", "/", root_dir, backend["id"])
        ok = bool(result.get("success"))
        message = result.get("message") or ""
    elif backend_type == "resource":
        resource_id = (backend.get("configData") or {}).get("resource_id")
        if not resource_id:
            raise UsageError("Backend 未配置 resource_id。")
        resources = api.list_resources()
        ok = any(r["id"] == resource_id for r in resources)
        message = f"资源存在: {resource_id[:8]}" if ok else f"资源不存在: {resource_id[:8]}"
        if args.json:
            output.print_json({"success": ok, "message": message})
        else:
            print(f"{'✅' if ok else '❌'} {message}")
        return 0 if ok else 1
    else:  # api
        if args.json:
            output.print_json({"success": False, "message": "API 类型 Backend 无服务端测试端点"})
        else:
            print("API 类型 Backend 由客户端主动连接，无服务端测试端点。", file=sys.stderr)
        return 1
    if args.json:
        output.print_json(result)
    else:
        print(f"{'✅ 连接正常' if ok else '❌ 连接失败'}: {message}")
    return 0 if ok else 1


@with_api
def cmd_ssh_key(args, api):
    result = api.get_ssh_public_key()
    if args.json:
        output.print_json(result)
        return 0
    print(result.get("public_key", ""))
    return 0


@with_api
def cmd_tool_set(args, api):
    backends = api.list_backends()
    backend = resolve_backend(backends, args.backend)
    tools_config = dict(backend.get("tools_config") or {})
    tool_cfg = dict(tools_config.get(args.tool_name) or {})
    if args.enabled is not None:
        tool_cfg["enabled"] = _parse_bool_flag("--enabled", args.enabled)
    if args.review_mode is not None:
        tool_cfg["require_review"] = args.review_mode == "require_review"
    if not tool_cfg:
        raise UsageError("至少提供一个要修改的参数（--enabled / --review-mode）")
    tools_config[args.tool_name] = tool_cfg
    updated = api.update_backend(backend["id"], {"tools_config": tools_config})
    if args.json:
        output.print_json(updated)
    else:
        print(f"已更新工具配置 '{args.tool_name}': {tools_config[args.tool_name]}")
    return 0
