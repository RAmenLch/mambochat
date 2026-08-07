"""mambo CLI 主入口。

用法: mambo [--base-url URL] [--timeout SEC] [--json] <domain> <action> [options]
"""
from __future__ import annotations

import argparse
import os
import sys

from backend.mambo_cli import __version__
from backend.mambo_cli.client import ApiError
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, format_parser_help
from backend.mambo_cli.resolver import ResolutionError
from backend.mambo_cli.util import UsageError

DEFAULT_BASE_URL = os.environ.get("MAMBO_BASE_URL", "http://127.0.0.1:8000")

SUBPARSERS: dict[str, argparse.ArgumentParser] = {}

COMMON_HELP = f"""MamboChat CLI v{__version__} — 常用命令（完整版: mambo help --all）

用法:
  mambo <domain> <action> [options]
  全局参数 --base-url / --timeout / --json 可放在任意位置

服务商 provider:
  list                        列出全部服务商
  add --name N --api-host H --api-key K [--id ID] [--use-proxy]
  update <provider> [--name N] [--api-host H] [--api-key K] [--use-proxy true|false]
  delete <provider> --yes     删除（需 --yes 确认）
  test <provider>             测试连通性

模型 model:
  list [--provider P] [--type chat|embedding]
  add --provider P --model-id MID [--name N] [--type chat|embedding] [--starred]
      （自动注入服务商元数据中的预设属性: name/类型/meta_config）
  update <model> [--name N] [--type T] [--starred true|false]
  delete <model> --yes        删除（需 --yes 确认）
  set-default <model>         设为全局默认模型

全局设置 settings:
  get [key]                   查看全局配置（可只查单项）
  set <key> <value>           修改配置项

资源 resource（文件系统式）:
  ls [路径]                   列出目录内容（[kb]/[skill]/[folder] 与 [file]/[prompt]/[template]）
  cat <路径>                  查看文件内容（默认截断 2000 字符）
  mkdir <路径>                创建普通文件夹
  update <路径> [--name N] [--description D]   修改名称/描述
  write <路径> --content <内容> | --file <本地文件>  创建/覆盖文件内容（写入即新版本）
  rm <路径> [-R] --yes        删除（目录需 -R 递归）
  mv <路径> <目标目录>        移动资源（仅移入语义）
  find <关键词> [--regex]     全局搜索资源内容

Skill skill:
  list                        列出全部 Skill
  create --name N --description D [--into 目录]
  validate <路径>             校验 Skill 规范
  delete <路径> -R --yes      删除 Skill 目录
  import --file <path|zip>|--github <url> --into 目录   （高级）

引用规则（Docker 风格前缀 ID）:
  provider: 完整ID / ID前缀(唯一即可) / 唯一名称
  model:    完整UUID / UUID前缀(唯一即可) / provider:modelId / 唯一modelId
  示例: 190c2f0c / 190 / 190c2f0c:deepseek-v4-flash / DeepSeek:deepseek-v4-flash
  资源:    短ID前缀 或 路径（/父目录/名称，/ 为资源根）

示例:
  mambo provider list
  mambo provider add --name OpenAI --api-host https://api.openai.com/v1 --api-key sk-xxx
  mambo model list
  mambo model add --provider openai --model-id gpt-4o --name "GPT-4o"
  mambo model set-default openai:gpt-4o
  mambo settings set default_temperature 0.7
  mambo settings get default_model_id
"""

FULL_HELP = COMMON_HELP + """
高级命令与参数:
  provider show <provider>              查看服务商详情（含模型）
  provider fetch-models <provider>      拉取外部模型列表（可管道导入）
  provider add --worker-type TYPE --model "MID[:NAME[:TYPE]]"...
  model show <model>                    查看模型详情（含 meta_config）
  model add/update 的 meta_config 参数: --context-length / --max-output-tokens /
        --max-retries / --request-timeout / --tokenizer / --supported-parameters /
        --input-modalities / --output-modalities / --embedding-dimension /
        --max-context-length
  settings unset <key>                  恢复配置项为默认值
  resource upload <本地文件> <路径>      上传文件（目录=新建，文件=更新内容）
  resource version list/set-active/delete <路径>   版本管理（仅文件型资源）
  skill import --file <path|zip>|--github <url> --into 目录 [--on-conflict error|overwrite|skip]
  各命令完整参数: mambo <domain> <action> --help-all

退出码:
  0 成功 / 1 API 或运行时错误 / 2 参数用法错误 / 3 引用歧义或未找到
"""


def build_common_parser() -> argparse.ArgumentParser:
    # 注意：全局参数必须用 default=SUPPRESS。
    # Python 3.11 的子命令解析用独立 namespace 再合并回父级，
    # 若子命令 parser 也注册了这些参数，非 SUPPRESS 的默认值会覆盖父级显式传入的值。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url", default=argparse.SUPPRESS, metavar="URL",
        help=f"后端地址（默认 {DEFAULT_BASE_URL}，可用环境变量 MAMBO_BASE_URL 覆盖）",
    )
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS, metavar="SEC", help="请求超时秒数（默认 30.0）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出（推荐 LLM 使用）")
    return common


def normalize_args(args: argparse.Namespace) -> None:
    """为 SUPPRESS 的全局参数补充默认值，供 with_api 与各命令函数直接使用。"""
    args.base_url = getattr(args, "base_url", None) or DEFAULT_BASE_URL
    args.timeout = getattr(args, "timeout", None) or 30.0
    args.json = bool(getattr(args, "json", False))


def print_parser_help(parser: argparse.ArgumentParser, show_advanced: bool = False) -> None:
    parser._print_message(format_parser_help(parser, show_advanced=show_advanced), sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    common = build_common_parser()
    parser = argparse.ArgumentParser(
        prog="mambo",
        add_help=False,
        parents=[common],
        formatter_class=LeveledHelpFormatter,
        description="MamboChat 管理 CLI（面向 LLM 的操作入口）",
        epilog="常用命令见: mambo help；完整版: mambo help --all",
    )
    parser.add_argument("--version", action="version", version=f"mambo {__version__} (MamboChat CLI)")
    add_leveled_help(parser)
    sub = parser.add_subparsers(dest="domain", metavar="<domain>", title="命令域")

    from backend.mambo_cli.domains import provider as provider_domain
    from backend.mambo_cli.domains import model as model_domain
    from backend.mambo_cli.domains import settings as settings_domain
    from backend.mambo_cli.domains import resource as resource_domain
    from backend.mambo_cli.domains import skill as skill_domain

    SUBPARSERS["provider"] = provider_domain.add_parser(sub, common)
    SUBPARSERS["model"] = model_domain.add_parser(sub, common)
    SUBPARSERS["settings"] = settings_domain.add_parser(sub, common)
    SUBPARSERS["resource"] = resource_domain.add_parser(sub, common)
    SUBPARSERS["skill"] = skill_domain.add_parser(sub, common)

    help_parser = sub.add_parser(
        "help", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="查看帮助（常用模式；--all 查看完整版）",
    )
    add_leveled_help(help_parser)
    help_parser.add_argument(
        "topic", nargs="?", choices=["provider", "model", "settings", "resource", "skill"],
        help="查看指定命令域帮助",
    )
    help_parser.add_argument("--all", action="store_true", dest="show_all", help="高级模式：显示全部命令与参数")
    help_parser.set_defaults(func=cmd_help)
    SUBPARSERS["help"] = help_parser

    return parser


def cmd_help(args):
    if getattr(args, "topic", None):
        print_parser_help(SUBPARSERS[args.topic], show_advanced=args.show_all)
        return 0
    print(FULL_HELP if args.show_all else COMMON_HELP)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    normalize_args(args)
    domain = getattr(args, "domain", None)
    if not domain:
        print_parser_help(parser)
        return 2
    func = getattr(args, "func", None)
    if func is None:
        # 如 `mambo provider`（未指定 action）：打印该命令域常用帮助
        print_parser_help(SUBPARSERS[domain])
        return 2
    try:
        return func(args)
    except UsageError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except ResolutionError as exc:
        print(f"错误: {exc.message}", file=sys.stderr)
        return 3
    except ApiError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
