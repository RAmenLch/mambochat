"""mambo model — 模型管理。"""
from __future__ import annotations

import argparse
import sys

from backend.mambo_cli.client import ApiError, with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import resolve_model, resolve_provider
from backend.mambo_cli.util import UsageError, parse_bool
from backend.mambo_cli.llm_params import build_definition_map

MODEL_TYPES = ["chat", "embedding"]

# meta_config 平铺参数定义：flag 名 -> (meta_config 字段, 是否逗号分隔列表, 帮助说明)
# dest 用独立命名（request_timeout），避免与全局 --timeout 的 dest 冲突
META_CONFIG_FLAGS = [
    ("--context-length", "context_length", False,
     "整数: 上下文窗口 token 数，如 128000"),
    ("--max-output-tokens", "max_output_tokens", False,
     "整数: 单次最大输出 token 数，如 16384"),
    ("--tokenizer", "tokenizer", False,
     "分词器: GPT/Gemini/Claude/Qwen3/DeepSeek/Llama3/Mistral/Cohere/Grok 等"),
    ("--input-modalities", "input_modalities", True,
     "逗号分隔列表，选项: audio,text,video,file,image"),
    ("--output-modalities", "output_modalities", True,
     "逗号分隔列表，选项: image,text"),
    ("--supported-parameters", "supported_parameters", True,
     "逗号分隔列表，合法项见系统配置 SUPPORTED_LLM_PARAMETERS"
     "（如 temperature,top_p,max_tokens,stop,seed）"),
    ("--embedding-dimension", "embedding_dimension", False,
     "整数: embedding 模型向量维度，如 1536/2560/4096"),
    ("--max-context-length", "max_context_length", False,
     "整数: embedding 模型最大上下文 token 数"),
    ("--max-retries", "max_retries", False,
     "整数 0-20: 请求重试次数，0=使用全局默认"),
    ("--request-timeout", "timeout", False,
     "整数 10-600 秒: 请求超时，不传=使用全局默认"),
]


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "model", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="模型管理（添加/修改/删除/设默认）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="model_action", metavar="<action>")

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

    lp = cmd("list", "列出模型（可按服务商/类型过滤）")
    lp.add_argument("--provider", metavar="P", help="只显示指定服务商下的模型（服务商引用）")
    lp.add_argument("--type", dest="model_type", choices=MODEL_TYPES, help="只显示指定类型")
    lp.set_defaults(func=cmd_list)

    ap = cmd("add", "为服务商添加模型（自动注入服务商元数据预设）")
    ap.add_argument("--provider", required=True, metavar="P", help="所属服务商（服务商引用）")
    ap.add_argument("--model-id", required=True, dest="model_id", metavar="MID", help="模型 ID，如 gpt-4o")
    ap.add_argument("--name", help="显示名称（缺省使用服务商元数据中的名称，否则等于模型 ID）")
    ap.add_argument("--type", dest="model_type", choices=MODEL_TYPES, default=None,
                    help="模型类型（缺省使用服务商元数据，否则 chat）")
    ap.add_argument("--starred", action="store_true", help="创建后标星")
    _add_meta_config_args(ap, advanced=True)
    ap.set_defaults(func=cmd_add)

    up = cmd("update", "修改模型信息（只更新传入的参数）")
    up.add_argument("model", help="模型引用（完整UUID/UUID前缀/provider:modelId/唯一modelId）")
    up.add_argument("--name", help="显示名称")
    up.add_argument("--type", dest="model_type", choices=MODEL_TYPES, help="模型类型")
    up.add_argument("--starred", metavar="true|false", type=str, help="是否标星")
    _add_meta_config_args(up, advanced=True)
    up.set_defaults(func=cmd_update)

    dp = cmd("delete", "删除模型")
    dp.add_argument("model", help="模型引用")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    sd = cmd("set-default", "设为全局默认模型")
    sd.add_argument("model", help="模型引用")
    sd.set_defaults(func=cmd_set_default)

    sp_cmd = cmd("show", "查看模型详情", advanced=True)
    sp_cmd.add_argument("model", help="模型引用")
    sp_cmd.set_defaults(func=cmd_show)

    return p


def _add_meta_config_args(parser, advanced: bool = True):
    for flag, field, is_list, desc in META_CONFIG_FLAGS:
        dest = "request_timeout" if field == "timeout" else field
        kwargs = dict(
            dest=dest,
            metavar=field.upper(),
            help=desc,
        )
        if not is_list and field in ("context_length", "max_output_tokens",
                                     "embedding_dimension", "max_context_length",
                                     "max_retries", "timeout"):
            kwargs["type"] = int
        add_arg(parser, flag, advanced=advanced, **kwargs)


def _build_meta_config(args) -> dict:
    meta = {}
    for _flag, field, is_list, _desc in META_CONFIG_FLAGS:
        dest = "request_timeout" if field == "timeout" else field
        value = getattr(args, dest, None)
        if value is None:
            continue
        if is_list:
            value = [part.strip() for part in str(value).split(",") if part.strip()]
            if not value:
                continue
        meta[field] = value
    return meta


def _validate_supported_parameters(meta: dict, api) -> None:
    """校验 meta_config.supported_parameters 的 key 均为系统定义的合法参数。"""
    keys = meta.get("supported_parameters")
    if not keys:
        return
    definitions = api.get_system_config().get("llm_parameters") or []
    valid = set(build_definition_map(definitions).keys())
    invalid = [k for k in keys if k not in valid]
    if invalid:
        raise UsageError(
            f"不支持的参数 key: {', '.join(invalid)}"
            "（合法 key 见系统配置 SUPPORTED_LLM_PARAMETERS）"
        )


@with_api
def cmd_list(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider) if args.provider else None
    models = [m for p in providers for m in p.get("models", [])]
    if provider:
        provider_ids = {provider["id"]}
        models = [m for m in models if m["providerId"] in provider_ids]
    if args.model_type:
        models = [m for m in models if m["model_type"] == args.model_type]
    if args.json:
        output.print_json(models)
        return 0
    # PROVIDER 列显示服务商名称；名称重复时附加短 ID 以消歧
    name_counts = {}
    for p in providers:
        name_counts[p["name"]] = name_counts.get(p["name"], 0) + 1
    provider_name = {p["id"]: p["name"] for p in providers}

    def fmt_provider(provider_id):
        name = provider_name.get(provider_id)
        if not name:
            return output.short_id(provider_id)
        if name_counts[name] > 1:
            return f"{name} ({output.short_id(provider_id)})"
        return name

    output.print_table(models, [
        ("id", "ID", output.short_id),
        ("providerId", "PROVIDER", fmt_provider),
        ("modelId", "MODEL ID", None),
        ("name", "NAME", None),
        ("model_type", "TYPE", None),
        ("starred", "STARRED", lambda v: "yes" if v else "no"),
    ])
    return 0


@with_api
def cmd_show(args, api):
    providers = api.list_providers()
    model = resolve_model(providers, args.model)
    if args.json:
        output.print_json(model)
    else:
        output.print_kv(model, ["id", "providerId", "modelId", "name", "model_type", "starred", "meta_config"])
    return 0


@with_api
def cmd_add(args, api):
    providers = api.list_providers()
    provider = resolve_provider(providers, args.provider)

    # 尝试从服务商元数据获取该模型的预设属性（name / model_type / meta_config），
    # 与前端“获取模型后点击新增”的注入逻辑保持一致；失败时降级为默认属性。
    preset = None
    try:
        fetched = api.fetch_provider_models(provider["id"], provider.get("use_proxy", False))
        preset = next((m for m in fetched if m.get("modelId") == args.model_id), None)
    except ApiError as exc:
        print(f"警告: 获取模型元数据失败，将使用默认属性添加: {exc}", file=sys.stderr)

    data = {
        "providerId": provider["id"],
        "modelId": args.model_id,
        "name": args.name or (preset.get("name") if preset else None) or args.model_id,
        "model_type": args.model_type or (preset.get("model_type") if preset else None) or "chat",
        "starred": args.starred,
    }
    # 预设 meta_config 为基底，用户显式传入的高级参数优先覆盖
    meta = dict(preset.get("meta_config") or {}) if preset else {}
    meta.update(_build_meta_config(args))
    _validate_supported_parameters(meta, api)
    if meta:
        data["meta_config"] = meta

    model = api.create_model(data)
    if args.json:
        output.print_json(model)
    else:
        output.print_kv(model, ["id", "providerId", "modelId", "name", "model_type", "starred"], label="已创建模型:")
        if preset:
            injected = [k for k in ("name", "model_type", "meta_config") if data.get(k)]
            print(f"已从服务商元数据注入预设属性: {', '.join(injected)}")
    return 0


@with_api
def cmd_update(args, api):
    providers = api.list_providers()
    model = resolve_model(providers, args.model)
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.model_type is not None:
        data["model_type"] = args.model_type
    if args.starred is not None:
        try:
            data["starred"] = parse_bool(args.starred)
        except argparse.ArgumentTypeError as exc:
            raise UsageError(f"{exc}")
    meta = _build_meta_config(args)
    _validate_supported_parameters(meta, api)
    if meta:
        data["meta_config"] = meta
    if not data:
        raise UsageError("至少提供一个要修改的参数（mambo model update --help 查看）")
    updated = api.update_model(model["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        output.print_kv(updated, ["id", "providerId", "modelId", "name", "model_type", "starred"], label="已更新模型:")
    return 0


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    providers = api.list_providers()
    model = resolve_model(providers, args.model)
    deleted = api.delete_model(model["id"])
    if args.json:
        output.print_json(deleted)
    else:
        print(f"已删除模型: {model['id']} ({model['modelId']})")
    return 0


@with_api
def cmd_set_default(args, api):
    providers = api.list_providers()
    model = resolve_model(providers, args.model)
    updated = api.update_global_settings({"default_model_id": model["id"]})
    if args.json:
        output.print_json(updated)
    else:
        print(f"已将默认模型设为: {model['providerId']} / {model['modelId']} ({model['id']})")
        print(f"default_model_id = {updated.get('default_model_id')}")
    return 0
