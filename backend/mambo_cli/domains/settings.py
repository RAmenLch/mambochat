"""mambo settings — 全局设置管理。"""
from __future__ import annotations

import argparse

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.resolver import resolve_model
from backend.mambo_cli.util import UsageError, parse_bool

# 可写配置项元数据：type 支持 model/bool/int/float/str/enum
SETTING_KEYS = {
    "default_model_id": {"type": "model", "desc": "全局默认模型（模型引用，如 openai:gpt-4o）"},
    "title_generation_model_id": {"type": "model", "desc": "标题生成模型（模型引用）"},
    "default_temperature": {"type": "float", "desc": "默认 Temperature"},
    "default_top_p": {"type": "float", "desc": "默认 Top P"},
    "default_stream": {"type": "bool", "desc": "默认是否流式输出"},
    "default_enable_suggest": {"type": "bool", "desc": "默认是否生成回复建议"},
    "default_enable_ask_user": {"type": "bool", "desc": "默认是否允许 AI 向用户提问"},
    "default_max_context_messages": {"type": "int", "desc": "默认上下文消息数量"},
    "default_max_retries": {"type": "int", "min": 1, "desc": "全局默认最大重试次数（>=1）"},
    "default_timeout": {"type": "int", "desc": "全局默认请求超时（秒）"},
    "proxy_enabled": {"type": "bool", "desc": "是否全局启用代理"},
    "proxy_url": {"type": "str", "desc": "代理服务器 URL，如 http://127.0.0.1:7890"},
    "web_search_default_mode": {
        "type": "enum", "choices": ["disable", "direct_read", "search_and_read"],
        "desc": "默认网页搜索模式",
    },
    "web_search_use_proxy": {"type": "bool", "desc": "网页搜索是否启用代理"},
    "zip_history_system_prompt": {"type": "str", "desc": "历史压缩 System Prompt"},
    "frontend_editor": {"type": "enum", "choices": ["simple", "monaco"], "desc": "前端编辑器类型"},
    "kb_default_chunk_size": {"type": "int", "desc": "知识库默认切片大小"},
    "kb_default_chunk_overlap": {"type": "int", "desc": "知识库默认切片重叠"},
    "send_message_shortcut": {"type": "enum", "choices": ["enter", "ctrl_enter"], "desc": "发送消息快捷键"},
    "language": {"type": "enum", "choices": ["zh-CN", "en"], "desc": "界面语言"},
}

# 只读（可查不可改）
READONLY_KEYS = ["user_avatar_url", "ai_avatar_url"]

COMMON_KEYS = [
    "default_model_id", "title_generation_model_id", "default_temperature",
    "default_top_p", "default_stream", "proxy_enabled", "proxy_url",
]

COMMON_KEYS_HINT = " / ".join(COMMON_KEYS)


def _key_line(key: str) -> str:
    meta = SETTING_KEYS.get(key)
    if not meta:
        return f"  {key}"
    hint = f"[{meta['type']}]"
    if meta["type"] == "enum":
        hint += " " + "/".join(meta["choices"])
    if "min" in meta:
        hint += f" >= {meta['min']}"
    return f"  {key:<34} {hint:<22} {meta.get('desc', '')}"


REFERENCE_RULES = """模型引用规则（用于 default_model_id / title_generation_model_id 等 [model] 字段）:
  1. 完整 UUID: 数据库主键
  2. UUID 前缀: 任意长度、唯一即可，如 090a8e57 或 090（Docker 风格）
  3. provider:modelId: 服务商短ID + ':' + 模型ID，彻底消歧，如 190c2f0c:deepseek-v4-flash
  4. 裸 modelId/name: 仅当全局唯一时可用
  查看短ID与所属服务商: mambo model list"""


def build_settings_epilogs() -> tuple[str, str]:
    common_lines = [_key_line(k) for k in COMMON_KEYS]
    all_lines = [_key_line(k) for k in SETTING_KEYS]
    common_text = ("可配置项（常用）:\n" + "\n".join(common_lines)
                   + "\n完整列表见 --help-all\n\n" + REFERENCE_RULES)
    all_text = ("可配置项（全部）:\n" + "\n".join(all_lines)
                + "\n只读项（可查不可改）: user_avatar_url / ai_avatar_url\n\n" + REFERENCE_RULES)
    return common_text, all_text


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "settings", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="全局设置管理（查看/修改）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="settings_action", metavar="<action>")

    g = sp.add_parser(
        "get", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="查看全局配置（可只查单项）",
    )
    add_leveled_help(g)
    g.add_argument("key", nargs="?", help="只查看单项（如 default_model_id）")
    g.set_defaults(func=cmd_get)

    s = sp.add_parser(
        "set", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="修改配置项",
    )
    add_leveled_help(s)
    s.add_argument("key", help=f"配置项（列表见下方；模型引用字段支持 openai:gpt-4o / UUID 前缀）")
    s.add_argument("value", help="新值（模型引用字段支持 openai:gpt-4o / UUID 前缀；null 表示清除）")
    s.set_defaults(func=cmd_set)

    u = sp.add_parser(
        "unset", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="[高级] 恢复配置项为默认值",
    )
    add_leveled_help(u)
    u.add_argument("key", help="配置项")
    u.set_defaults(func=cmd_unset)
    mark_advanced(u)

    epilog_common, epilog_all = build_settings_epilogs()
    p.help_epilog_common = epilog_common
    p.help_epilog_all = epilog_all
    s.help_epilog_common = epilog_common
    s.help_epilog_all = epilog_all

    return p


def _key_hint(key: str) -> str:
    meta = SETTING_KEYS.get(key)
    if not meta:
        return key
    hint = f"[{meta['type']}]"
    if meta["type"] == "enum":
        hint += " " + "/".join(meta["choices"])
    if "min" in meta:
        hint += f" (>= {meta['min']})"
    return f"{key} {hint}"


def _model_display(providers: list[dict], model_id: str) -> str | None:
    """模型 UUID -> 可读引用（provider短ID:modelId (provider名:modelId)）；找不到返回 None。"""
    for p in providers:
        for m in p.get("models", []):
            if m["id"] == model_id:
                return f"{p['id'][:8]}:{m['modelId']} ({p['name']}:{m['modelId']})"
    return None


@with_api
def cmd_get(args, api):
    settings = api.get_global_settings()
    if args.key:
        if args.key not in SETTING_KEYS and args.key not in READONLY_KEYS:
            raise UsageError(
                f"未知配置项 '{args.key}'。可用 mambo settings get 查看全部，"
                f"mambo settings --help-all 查看完整列表。"
            )
        if args.json:
            output.print_json({args.key: settings.get(args.key)})
        else:
            output.print_kv({args.key: settings.get(args.key)})
            # 模型引用字段附加解析注释（UUID -> 可读实体）
            meta = SETTING_KEYS.get(args.key)
            value = settings.get(args.key)
            if meta and meta["type"] == "model" and value:
                display = _model_display(api.list_providers(), value)
                if display:
                    print(f"  ↳ {display}")
        return 0
    if args.json:
        output.print_json(settings)
        return 0
    rows = []
    providers = None
    for key in SETTING_KEYS:
        if key not in settings:
            continue
        value = settings.get(key)
        if value and SETTING_KEYS[key]["type"] == "model":
            if providers is None:
                providers = api.list_providers()
            display = _model_display(providers, value)
            if display:
                value = display
        rows.append({"key": _key_hint(key), "value": value})
    for key in READONLY_KEYS:
        if key in settings:
            rows.append({"key": f"{key} (只读)", "value": settings.get(key)})
    output.print_table(rows, [("key", "KEY", None), ("value", "VALUE", None)])
    return 0


@with_api
def cmd_set(args, api):
    meta = SETTING_KEYS.get(args.key)
    if not meta:
        raise UsageError(
            f"未知配置项 '{args.key}'。可用 mambo settings --help-all 查看全部可配置项。"
        )
    raw = args.value
    value = raw
    resolved_model = None
    if meta["type"] == "model":
        if raw.strip().lower() in ("null", "none", ""):
            value = None
        else:
            providers = api.list_providers()
            model = resolve_model(providers, raw)
            value = model["id"]
            resolved_model = model
    elif meta["type"] == "bool":
        try:
            value = parse_bool(raw)
        except argparse.ArgumentTypeError as exc:
            raise UsageError(f"{exc}")
    elif meta["type"] == "int":
        try:
            value = int(raw)
        except ValueError:
            raise UsageError(f"'{raw}' 不是整数")
        if value < meta.get("min", float("-inf")):
            raise UsageError(f"{args.key} 必须 >= {meta['min']}")
    elif meta["type"] == "float":
        try:
            value = float(raw)
        except ValueError:
            raise UsageError(f"'{raw}' 不是数字")
    elif meta["type"] == "enum":
        if raw not in meta["choices"]:
            raise UsageError(f"'{raw}' 无效，可选 {'/'.join(meta['choices'])}")

    updated = api.update_global_settings({args.key: value})
    if args.json:
        output.print_json(updated)
    else:
        print(f"已设置 {args.key} = {value}")
        if resolved_model is not None:
            print(f"  ↳ 模型引用解析: {raw} → "
                  f"{resolved_model['providerId'][:8]}:{resolved_model['modelId']} "
                  f"(id:{resolved_model['id']})")
        output.print_kv({args.key: updated.get(args.key)})
    return 0


@with_api
def cmd_unset(args, api):
    if args.key not in SETTING_KEYS:
        raise UsageError(
            f"未知配置项 '{args.key}'。可用 mambo settings --help-all 查看全部可配置项。"
        )
    api.update_global_settings({args.key: None})
    print(f"已恢复 {args.key} 为默认值")
    return 0
