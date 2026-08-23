"""mambo mcp — MCP 服务器与工具管理。"""
from __future__ import annotations

import argparse
import re
import sys

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import resolve_mcp_server, resolve_mcp_tool
from backend.mambo_cli.util import UsageError, parse_bool

TRANSPORT_TYPES = ["stdio", "sse", "streamable_http"]
HTTP_TRANSPORTS = ("sse", "streamable_http")
REVIEW_MODES = ["none", "require_review"]

_SERVER_KV_KEYS = ["id", "name", "description", "transportType", "isEnabled", "useProxy", "isSystem",
                   "command", "args", "env", "cwd", "url", "headers",
                   "timeout", "sse_read_timeout", "last_status", "last_test_at", "last_error"]
_SERVER_SUMMARY_KEYS = ["id", "name", "transportType", "isEnabled"]
_TOOL_KEYS = ["id", "server_id", "name", "is_enabled", "review_mode", "status"]


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "mcp", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="MCP 服务器与工具管理（添加/修改/测试/同步）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="mcp_action", metavar="<action>")

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

    lp = cmd("list", "列出全部 MCP 服务器（含系统内置）")
    lp.add_argument("--enabled-only", action="store_true", help="只显示已启用的服务器")
    lp.set_defaults(func=cmd_list)

    sp_cmd = cmd("show", "查看 MCP 服务器详情（含完整配置）")
    sp_cmd.add_argument("server", help="MCP 服务器引用（完整ID/ID前缀/唯一名称）")
    sp_cmd.set_defaults(func=cmd_show)

    ap = cmd("add", "创建 MCP 服务器（stdio 或 sse/streamable_http）")
    _add_server_args(ap, create=True)
    ap.set_defaults(func=cmd_add)

    up = cmd("update", "修改 MCP 服务器配置（只更新传入的参数；传 \"\" 清空列表/字典）")
    up.add_argument("server", help="MCP 服务器引用")
    _add_server_args(up, create=False)
    up.set_defaults(func=cmd_update)

    dp = cmd("delete", "删除 MCP 服务器（连带其工具元数据）")
    dp.add_argument("server", help="MCP 服务器引用")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    tp = cmd("test", "测试 MCP 服务器连接（healthy=0 / unhealthy=1）")
    tp.add_argument("server", help="MCP 服务器引用")
    tp.set_defaults(func=cmd_test)

    tc = cmd("test-config", "不保存直接测试 MCP 配置（无需名称）", advanced=True)
    _add_test_config_args(tc)
    tc.set_defaults(func=cmd_test_config)

    sy = cmd("sync", "同步 MCP 服务器工具列表到数据库")
    sy.add_argument("server", help="MCP 服务器引用")
    sy.set_defaults(func=cmd_sync)

    tl = cmd("tools", "列出 MCP 服务器下已同步的工具")
    tl.add_argument("server", help="MCP 服务器引用")
    tl.set_defaults(func=cmd_tools)

    tu = cmd("tool", "管理 MCP 工具（update/delete）")
    tsp = tu.add_subparsers(dest="mcp_tool_action", metavar="<tool-action>")

    def tcmd(name, help_text):
        cp = tsp.add_parser(
            name, parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
            help=help_text,
        )
        add_leveled_help(cp)
        return cp

    tup = tcmd("update", "修改工具启停状态与审核模式")
    tup.add_argument("tool", help="工具引用（完整UUID/UUID前缀/唯一工具名）")
    tup.add_argument("--enable", metavar="true|false", help="是否启用")
    tup.add_argument("--review-mode", dest="review_mode", choices=REVIEW_MODES, help="审核模式")
    tup.set_defaults(func=cmd_tool_update)

    tdel = tcmd("delete", "删除失效（offline）的 MCP 工具")
    tdel.add_argument("tool", help="工具引用")
    tdel.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    tdel.set_defaults(func=cmd_tool_delete)

    return p


def _add_transport_args(parser, clearable: bool) -> None:
    """传输类型相关参数（add/update/test-config 共用）。clearable=True 时列表/字典支持 \"\" 清空。"""
    clear_hint = "（update 传 \"\" 清空全部）" if clearable else ""
    parser.add_argument("--command", help="stdio: 启动命令，如 python / npx / uvx")
    add_arg(parser, "--arg", action="append", metavar="A",
            help=f"stdio: 启动参数，可重复{clear_hint}；以 - 开头的值须用 --arg=值 形式（如 --arg=-y）")
    add_arg(parser, "--env", action="append", metavar="KEY=VALUE",
            help=f"stdio: 环境变量，可重复{clear_hint}")
    add_arg(parser, "--cwd", help="stdio: 工作目录")
    parser.add_argument("--url", help="sse/streamable_http: 服务地址，如 http://host:8000/sse")
    add_arg(parser, "--header", action="append", metavar="KEY=VALUE",
            help=f"http: 请求头，可重复{clear_hint}；支持 KEY=VALUE 或 KEY: VALUE 形式")
    parser.add_argument("--http-timeout", dest="http_timeout", type=float, metavar="SEC",
                        help="http: 请求超时（秒）")
    parser.add_argument("--sse-read-timeout", dest="sse_read_timeout", type=float, metavar="SEC",
                        help="http: SSE 读取超时（秒）")


def _add_server_args(parser, create: bool) -> None:
    if create:
        parser.add_argument("--name", required=True,
                            help="名称（字母开头，仅字母/数字/_/-，≤64）")
    else:
        parser.add_argument("--name", help="名称（字母开头，仅字母/数字/_/-，≤64）")
    parser.add_argument("--description", help="描述")
    parser.add_argument("--transport", dest="transport_type", choices=TRANSPORT_TYPES,
                        help=f"传输类型（默认 stdio，可选 {'/'.join(TRANSPORT_TYPES)}）")
    _add_transport_args(parser, clearable=not create)
    if create:
        parser.add_argument("--use-proxy", action="store_true",
                            help="启用全局代理（仅 http 传输；缺省直连并屏蔽环境变量代理）")
        parser.add_argument("--disable", action="store_true", help="创建后禁用")
    else:
        parser.add_argument("--use-proxy", type=parse_bool, metavar="true|false",
                            help="是否启用全局代理（仅 http 传输；false=直连并屏蔽环境变量代理）")
        parser.add_argument("--enable", type=parse_bool, metavar="true|false",
                            help="是否启用")


def _add_test_config_args(parser) -> None:
    """test-config 专用参数：仅传输配置，无名称/描述/启停等创建性参数。"""
    parser.add_argument("--transport", dest="transport_type", choices=TRANSPORT_TYPES,
                        help=f"传输类型（默认 stdio，可选 {'/'.join(TRANSPORT_TYPES)}）")
    _add_transport_args(parser, clearable=False)
    parser.add_argument("--use-proxy", action="store_true",
                        help="启用全局代理（仅 http 传输；缺省直连并屏蔽环境变量代理）")


def _build_list(values, create: bool):
    """create 时直接转 list；update 时传单个 \"\" 表示清空。返回 None 表示未传。"""
    if values is None:
        return None
    if not create and len(values) == 1 and values[0] == "":
        return []
    return list(values)


def _build_kv(values, flag: str, create: bool, allow_colon: bool = False):
    """解析 KEY=VALUE 列表为字典；update 时传单个 \"\" 表示清空。返回 None 表示未传。

    allow_colon=True 时（--header）同时接受 KEY: VALUE 冒号形式，值两侧空白将被去除。
    """
    if values is None:
        return None
    if not create and len(values) == 1 and values[0] == "":
        return {}
    result = {}
    for item in values:
        sep_idx = item.find("=")
        sep = "="
        if sep_idx == -1 and allow_colon:
            sep_idx = item.find(":")
            sep = ":"
        if sep_idx == -1:
            raise UsageError(f"{flag} 需要 KEY=VALUE 形式: '{item}'")
        key = item[:sep_idx].strip()
        if not key:
            raise UsageError(f"{flag} 的 KEY 不能为空: '{item}'")
        value = item[sep_idx + 1:]
        if sep == ":":
            value = value.strip()
        result[key] = value
    return result


def _build_transport_fields(args, create: bool) -> dict:
    """构建传输类型相关字段（command/args/env/cwd/url/headers/timeout/sse_read_timeout）。"""
    data = {}
    if args.command is not None:
        data["command"] = args.command
    arg_list = _build_list(args.arg, create)
    if arg_list is not None:
        data["args"] = arg_list
    env = _build_kv(args.env, "--env", create)
    if env is not None:
        data["env"] = env
    if args.cwd is not None:
        data["cwd"] = args.cwd
    if args.url is not None:
        data["url"] = args.url
    headers = _build_kv(args.header, "--header", create, allow_colon=True)
    if headers is not None:
        data["headers"] = headers
    if args.http_timeout is not None:
        data["timeout"] = args.http_timeout
    if args.sse_read_timeout is not None:
        data["sse_read_timeout"] = args.sse_read_timeout
    return data


def _build_server_data(args, create: bool) -> dict:
    data = {}
    if create:
        data["name"] = args.name
        data["transportType"] = args.transport_type or "stdio"
        data["isEnabled"] = not args.disable
        data["useProxy"] = bool(args.use_proxy)
    else:
        if args.name is not None:
            data["name"] = args.name
        if args.transport_type is not None:
            data["transportType"] = args.transport_type
        if args.enable is not None:
            data["isEnabled"] = args.enable
        if args.use_proxy is not None:
            data["useProxy"] = args.use_proxy
    if args.description is not None:
        data["description"] = args.description
    data.update(_build_transport_fields(args, create))
    return data


def _build_test_config_data(args) -> dict:
    """test-config 专用：不保存，无需名称/描述/启停；name 用临时值满足后端 schema 校验。"""
    data = {
        "name": "test-config",
        "transportType": args.transport_type or "stdio",
        "useProxy": bool(args.use_proxy),
    }
    data.update(_build_transport_fields(args, create=True))
    return data


def _validate_transport(data: dict) -> None:
    transport = data["transportType"]
    if transport == "stdio":
        if not data.get("command"):
            raise UsageError("stdio 传输需要 --command（如 python / npx）")
    elif not data.get("url"):
        raise UsageError(f"{transport} 传输需要 --url")


_ERROR_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Timeout|Refused|Failed|Unavailable)(:.*)?$")


def _extract_error_cause(error: str) -> str:
    """从后端返回的错误（可能含完整 asyncio 异常组 traceback）中提取根因摘要。

    异常组的首行（如 "unhandled errors in a TaskGroup (1 sub-exception)"）只是
    通用包装语；真正原因是最深层叶子异常（如 httpx.ConnectError），
    从 traceback 末尾向上取最后一个异常类名行。
    """
    if not error:
        return "未知错误"
    text = str(error)
    lines = text.splitlines()
    if not any("Traceback" in line or "Exception Group" in line for line in lines):
        return text
    for line in reversed(lines):
        # 去掉 traceback 装饰前缀（| + - 与空白），再匹配异常类名行
        stripped = line.strip(" |+-\t")
        if _ERROR_LINE_RE.match(stripped):
            return stripped
    return text


def _print_test_result(result: dict, args) -> None:
    if args.json:
        output.print_json(result)
        return
    if result.get("status") == "healthy":
        print(f"连接正常 (healthy): 发现 {result.get('tools_count', 0)} 个工具")
    else:
        error = result.get("error") or result.get("message") or ""
        print(f"连接失败 (unhealthy): {_extract_error_cause(error)}")
        print("完整错误见 mcp test --json", file=sys.stderr)


def _print_tools_table(tools) -> None:
    output.print_table(tools, [
        ("id", "ID", output.short_id),
        ("name", "NAME", None),
        ("status", "STATUS", None),
        ("is_enabled", "ENABLED", lambda v: "yes" if v else "no"),
        ("review_mode", "REVIEW", None),
    ])


def _load_all_tools(api):
    """遍历全部服务器收集工具列表，供 tool 引用解析。"""
    tools = []
    for server in api.list_mcp_servers():
        tools.extend(api.list_mcp_tools(server["id"]))
    return tools


@with_api
def cmd_list(args, api):
    servers = api.list_mcp_servers()
    if args.enabled_only:
        servers = [s for s in servers if s.get("isEnabled")]
    if args.json:
        output.print_json(servers)
        return 0
    output.print_table(servers, [
        ("id", "ID", output.short_id),
        ("name", "NAME", None),
        ("transportType", "TRANSPORT", None),
        ("isEnabled", "ENABLED", lambda v: "yes" if v else "no"),
        ("last_status", "STATUS", lambda v: v or "-"),
        ("isSystem", "SYS", lambda v: "system" if v else ""),
    ])
    return 0


@with_api
def cmd_show(args, api):
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    if args.json:
        output.print_json(server)
        return 0
    output.print_kv(server, _SERVER_KV_KEYS, label="MCP 服务器:")
    return 0


@with_api
def cmd_add(args, api):
    data = _build_server_data(args, create=True)
    _validate_transport(data)
    server = api.create_mcp_server(data)
    if args.json:
        output.print_json(server)
    else:
        output.print_kv(server, _SERVER_SUMMARY_KEYS, label="已创建 MCP 服务器:")
    return 0


@with_api
def cmd_update(args, api):
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    if server.get("isSystem"):
        raise UsageError("系统内置 MCP 服务器只读，禁止修改。")
    data = _build_server_data(args, create=False)
    if not data:
        raise UsageError("至少提供一个要修改的参数（mambo mcp update --help 查看）")
    updated = api.update_mcp_server(server["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        output.print_kv(updated, _SERVER_SUMMARY_KEYS, label="已更新 MCP 服务器:")
    return 0


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    if server.get("isSystem"):
        raise UsageError("系统内置 MCP 服务器只读，禁止删除。")
    api.delete_mcp_server(server["id"])
    if args.json:
        output.print_json({"deleted": server["id"]})
    else:
        print(f"已删除 MCP 服务器: {server['id']} ({server['name']})")
    return 0


@with_api
def cmd_test(args, api):
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    result = api.test_mcp_server(server["id"])
    _print_test_result(result, args)
    return 0 if result.get("status") == "healthy" else 1


@with_api
def cmd_test_config(args, api):
    data = _build_test_config_data(args)
    _validate_transport(data)
    result = api.test_mcp_config(data)
    _print_test_result(result, args)
    return 0 if result.get("status") == "healthy" else 1


@with_api
def cmd_sync(args, api):
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    tools = api.sync_mcp_tools(server["id"])
    if args.json:
        output.print_json(tools)
        return 0
    print(f"已同步 MCP 服务器 '{server['name']}' 的工具（{len(tools)}）:")
    _print_tools_table(tools)
    return 0


@with_api
def cmd_tools(args, api):
    servers = api.list_mcp_servers()
    server = resolve_mcp_server(servers, args.server)
    tools = api.list_mcp_tools(server["id"])
    if args.json:
        output.print_json(tools)
        return 0
    print(f"工具列表（{server['name']}，共 {len(tools)}）:")
    _print_tools_table(tools)
    return 0


@with_api
def cmd_tool_update(args, api):
    tools = _load_all_tools(api)
    tool = resolve_mcp_tool(tools, args.tool)
    data = {}
    if args.enable is not None:
        try:
            data["is_enabled"] = parse_bool(args.enable)
        except argparse.ArgumentTypeError as exc:
            raise UsageError(f"{exc}")
    if args.review_mode is not None:
        data["review_mode"] = args.review_mode
    if not data:
        raise UsageError("至少提供一个要修改的参数（--enable / --review-mode）")
    updated = api.update_mcp_tool(tool["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        output.print_kv(updated, _TOOL_KEYS, label="已更新工具:")
    return 0


@with_api
def cmd_tool_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    tools = _load_all_tools(api)
    tool = resolve_mcp_tool(tools, args.tool)
    api.delete_mcp_tool(tool["id"])
    if args.json:
        output.print_json({"deleted": tool["id"]})
    else:
        print(f"已删除工具: {tool['id']} ({tool['name']})")
    return 0
