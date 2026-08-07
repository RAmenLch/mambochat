"""mambo provider — 服务商管理。"""
from __future__ import annotations

import argparse
import sys

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import resolve_provider
from backend.mambo_cli.util import UsageError, parse_bool

WORKER_TYPES = ["openai", "google", "deepseek", "anthropic"]
MODEL_TYPES = ["chat", "embedding"]


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "provider", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="服务商管理（添加/修改/删除/测试）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="provider_action", metavar="<action>")

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

    lp = cmd("list", "列出全部服务商及模型数")
    lp.set_defaults(func=cmd_list)

    ap = cmd("add", "创建服务商（可附带模型）")
    ap.add_argument("--name", required=True, help="显示名称")
    ap.add_argument("--api-host", required=True, dest="api_host", metavar="HOST", help="API Host，如 https://api.openai.com/v1")
    ap.add_argument("--api-key", required=True, dest="api_key", metavar="KEY", help="API Key")
    ap.add_argument("--id", metavar="ID", help="自定义 ID（如 openai），缺省自动生成 UUID")
    add_arg(ap, "--use-proxy", action="store_true", help="为此服务商启用代理")
    add_arg(ap, "--worker-type", choices=WORKER_TYPES, default="openai", advanced=True, help="Worker 类型")
    add_arg(ap, "--model", action="append", metavar="MODELID[:NAME[:TYPE]]", advanced=True,
            help="随服务商批量创建模型，可重复指定")
    ap.set_defaults(func=cmd_add)

    up = cmd("update", "修改服务商信息（只更新传入的参数）")
    up.add_argument("provider", help="服务商引用（完整ID/UUID前缀/唯一名称）")
    up.add_argument("--name", help="显示名称")
    up.add_argument("--api-host", dest="api_host", metavar="HOST", help="API Host")
    up.add_argument("--api-key", dest="api_key", metavar="KEY", help="API Key")
    up.add_argument("--use-proxy", type=str, metavar="true|false", help="是否启用代理")
    add_arg(up, "--worker-type", choices=WORKER_TYPES, advanced=True, help="Worker 类型")
    up.set_defaults(func=cmd_update)

    dp = cmd("delete", "删除服务商（连带其全部模型）")
    dp.add_argument("provider", help="服务商引用")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    tp = cmd("test", "测试服务商连通性")
    tp.add_argument("provider", help="服务商引用")
    tp.add_argument("--use-proxy", action="store_true", help="测试时使用代理")
    tp.set_defaults(func=cmd_test)

    sp_cmd = cmd("show", "查看单个服务商详情（含模型列表）", advanced=True)
    sp_cmd.add_argument("provider", help="服务商引用")
    sp_cmd.set_defaults(func=cmd_show)

    fp = cmd("fetch-models", "拉取服务商可用的外部模型列表", advanced=True)
    fp.add_argument("provider", help="服务商引用")
    fp.add_argument("--use-proxy", action="store_true", help="拉取时使用代理")
    fp.set_defaults(func=cmd_fetch_models)

    return p


def _print_provider(provider: dict, as_json: bool) -> None:
    if as_json:
        output.print_json(provider)
    else:
        output.print_kv(provider, ["id", "name", "apiHost", "worker_type", "use_proxy"])


@with_api
def cmd_list(args, api):
    providers = api.list_providers()
    if args.json:
        output.print_json(providers)
        return 0
    output.print_table(providers, [
        ("id", "ID", output.short_id),
        ("name", "NAME", None),
        ("apiHost", "API HOST", None),
        ("worker_type", "WORKER", None),
        ("use_proxy", "PROXY", lambda v: "yes" if v else "no"),
        ("models", "MODELS", lambda v: str(len(v)) if isinstance(v, list) else str(v or 0)),
    ])
    return 0


@with_api
def cmd_show(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)
    if args.json:
        output.print_json(provider)
        return 0
    output.print_kv(provider, ["id", "name", "apiHost", "worker_type", "use_proxy", "apiKey"], label="服务商:")
    models = provider.get("models") or []
    print(f"\n模型 ({len(models)}):")
    output.print_table(models, [
        ("id", "ID", output.short_id),
        ("modelId", "MODEL ID", None),
        ("name", "NAME", None),
        ("model_type", "TYPE", None),
        ("starred", "STARRED", lambda v: "yes" if v else "no"),
    ])
    return 0


@with_api
def cmd_add(args, api):
    data = {
        "name": args.name,
        "apiHost": args.api_host,
        "apiKey": args.api_key,
        "use_proxy": args.use_proxy,
        "worker_type": args.worker_type,
    }
    if args.id:
        data["id"] = args.id
    models = []
    for spec in args.model or []:
        parts = spec.split(":")
        if len(parts) == 1:
            model_id, name, mtype = parts[0], parts[0], "chat"
        elif len(parts) == 2:
            model_id, name, mtype = parts[0], parts[1], "chat"
        else:
            model_id, name, mtype = parts[0], parts[1], parts[2]
        if mtype not in MODEL_TYPES:
            raise UsageError(f"模型类型 '{mtype}' 无效（可选 {'/'.join(MODEL_TYPES)}）")
        models.append({"modelId": model_id, "name": name, "model_type": mtype, "starred": False})
    if models:
        data["models"] = models
    provider = api.create_provider(data)
    if args.json:
        output.print_json(provider)
    else:
        _print_provider(provider, False)
        print(f"已创建服务商，含 {len(models)} 个模型。")
    return 0


@with_api
def cmd_update(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.api_host is not None:
        data["apiHost"] = args.api_host
    if args.api_key is not None:
        data["apiKey"] = args.api_key
    if args.use_proxy is not None:
        try:
            data["use_proxy"] = parse_bool(args.use_proxy)
        except argparse.ArgumentTypeError as exc:
            raise UsageError(f"{exc}")
    if args.worker_type is not None:
        data["worker_type"] = args.worker_type
    if not data:
        raise UsageError("至少提供一个要修改的参数（mambo provider update --help 查看）")
    updated = api.update_provider(provider["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        _print_provider(updated, False)
    return 0


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)
    deleted = api.delete_provider(provider["id"])
    if args.json:
        output.print_json(deleted)
    else:
        print(f"已删除服务商: {provider['id']} ({provider['name']})")
    return 0


@with_api
def cmd_test(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)
    result = api.test_provider(provider["id"], provider["apiHost"], args.use_proxy)
    if args.json:
        output.print_json(result)
    else:
        output.print_kv(result)
    return 0 if result.get("status") == "success" else 1


@with_api
def cmd_fetch_models(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)
    models = api.fetch_provider_models(provider["id"], args.use_proxy)
    if args.json:
        output.print_json(models)
        return 0
    output.print_table(models, [
        ("modelId", "MODEL ID", None),
        ("name", "NAME", None),
        ("model_type", "TYPE", None),
    ])
    print(f"\n提示: 可用 mambo model add --provider {provider['id']} --model-id <ID> 导入。", file=sys.stderr)
    return 0
