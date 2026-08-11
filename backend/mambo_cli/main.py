"""mambo CLI 主入口。

用法: mambo [--base-url URL] [--timeout SEC] [--json] <domain> <action> [options]
"""
from __future__ import annotations

import argparse
import os
import sys

from backend.mambo_cli import __version__
from backend.mambo_cli import output
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

MCP 服务器 mcp:
  list [--enabled-only]       列出全部服务器（含系统内置，只读）
  show <server>               查看服务器详情（含完整配置）
  add --name N                创建服务器
      stdio:  --command C [--arg A]... [--env K=V]... [--cwd DIR]
      http:   --transport sse|streamable_http --url U [--header K=V]...
              [--use-proxy]   启用全局代理（缺省直连，屏蔽环境变量代理）
  update <server> [--name N] [--enable true|false] [--use-proxy true|false] ...
      （列表/字典传 "" 清空，如 --env ""）
  delete <server> --yes       删除（需 --yes 确认）
  test <server>               测试连接（healthy=0 / unhealthy=1）
  sync <server>               同步工具列表到数据库
  tools <server>              列出已同步的工具
  tool update <tool> [--enable true|false] [--review-mode none|require_review]
  tool delete <tool> --yes    删除 offline 工具

Agent agent（树形目录，路径寻址）:
  list [--tree] [--path 目录]  列出 Agent（树状展示/按目录过滤）
  show <agent>                 查看配置详情（模型/挂载解析为可读引用）
  mkdir <路径>                 创建文件夹
  create <路径> [--type Mambo|ReActAgent] [--model M] [--description D]
      [--system-prompt-content TEXT | --system-prompt-filepath PATH]
  update <agent> [--name N] [--description D] [--type T] [--model M] [--default-backend B]
      [--system-prompt-content TEXT | --system-prompt-filepath PATH] [--clear-system-prompt]
  delete <agent> -R --yes      删除（文件夹需 -R 递归）
  mv <agent> <目标目录>        移动 Agent 或文件夹（/ 或 root 表示根）
  duplicate <agent>            复制 Agent（名称自动加 -副本）
  export <agent> [--output PATH]   导出为 .mamboagent 包（含子 Agent/挂载依赖）
  import --file PATH [--into 目录] [--preview] [--name-override K=V]... [--yes]
      （同名冲突自动改名；存在改名建议时需 --yes 确认；--preview 仅预检不写入）
  mount <agent> [--resource R]... [--mcp S]... [--backend B]... [--memory-resource R]...
  unmount <agent> ...          移除挂载（参数同 mount）
  subagent add|remove <agent> <子Agent>...   管理子 Agent

Backend backend（SSH/API/Resource/Local 文件后端）:
  list [--type ssh|api|resource|local]   列出全部 Backend
  show <backend>                         查看详情（密码/API Key 脱敏）
  add --name N --type ssh|api|resource|local [类型参数] [--description D]
      ssh:      --hostname H --username U [--port 22] [--password PW] [--root-dir /]
      api:      --api-key K
      resource: --resource R
      local:    [--root-dir ~]
      通用:     --edit-whitelist A,B / --edit-blacklist A,B / --ignore-dirs A,B
      工具:     [--execute-enabled true|false] [--execute-review true|false]
  update <backend> [--name N] [--description D] [类型参数]（列表传 "" 清空）
  delete <backend> --yes       删除（需 --yes 确认）
  duplicate <backend>          复制 Backend
  test <backend>               测试连接（ssh=真实连接 / local=目录校验 / resource=资源校验 / api=不支持）
  ssh-key                      显示系统全局 SSH 公钥（配置免密登录用）

引用规则（名称/路径优先，UUID 仅兜底）:
  provider:    唯一名称 / ID前缀
  model:       provider:modelId（如 openai:gpt-4o）/ 唯一 modelId
  resource:    绝对路径 /父目录/名称；唯一名称
  skill:       Skill 目录路径（同 resource）
  agent:       绝对路径 /父目录/名称；唯一名称
  mcp server:  唯一名称（system-* 为系统内置，只读）
  mcp tool:    唯一工具名
  backend:     唯一名称
  名称重名时报错并列出候选；完整UUID / 短ID前缀 始终可用作兜底

示例:
  mambo provider list
  mambo provider add --name OpenAI --api-host https://api.openai.com/v1 --api-key sk-xxx
  mambo model list
  mambo model add --provider openai --model-id gpt-4o --name "GPT-4o"
  mambo model set-default openai:gpt-4o
  mambo settings set default_temperature 0.7
  mambo settings get default_model_id
  mambo mcp add --name filesystem --command npx --arg=-y --arg=@modelcontextprotocol/server-filesystem
  mambo mcp sync filesystem
  mambo mcp tools filesystem
  mambo agent mkdir /团队
  mambo agent create /团队/数据分析师 --model openai:gpt-4o --system-prompt-filepath ./prompt.md
  mambo agent mount /团队/数据分析师 --resource /知识库/产品文档 --backend ssh-prod --mcp filesystem
  mambo agent export /团队/数据分析师 --output ./backup
  mambo agent import --file ./backup/数据分析师.mamboagent --into /团队 --preview
  mambo agent import --file ./backup/数据分析师.mamboagent --into /团队 --yes
  mambo backend add --name ssh-prod --type ssh --hostname 10.0.0.5 --username root
  mambo backend test ssh-prod
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
  mcp test-config ...            [高级] 不保存直接测试配置（无需名称，仅传输配置）
  mcp 传输类型: stdio（本地进程）; sse / streamable_http（远程 HTTP）
  mcp update 清空约定: 列表/字典传 ""（如 --arg "" / --env "" / --header ""）
  agent update 平铺参数: --planning / --memory / --summarization / --show / --general-purpose
        true|false；--mcp-tool-threshold N；AI 安全审核: --review-enabled / --review-model /
        --review-tools T...；摘要配置: --summary-trigger-type/value、--summary-keep-type/value、
        --summary-offload；模型参数: --param KEY=VALUE（可重复）
  agent hitl-tools <agent>        查看可纳入 AI 安全审核的工具列表
  agent params <agent>            查看该 Agent 的建议模型参数（key/类型/范围/默认值/当前值）
  agent import-cleanup <会话ID> --yes   清理一次导入会话创建的实体（导入失败后回滚）
  backend tool set <backend> <工具名> --enabled true|false --review-mode none|require_review
  backend 密码语义: update 传 "********" 保持原密码，传 "" 清空为免密
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
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出（推荐 LLM 使用；错误亦以 JSON 输出至 stderr）")
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
    from backend.mambo_cli.domains import mcp as mcp_domain
    from backend.mambo_cli.domains import agent as agent_domain
    from backend.mambo_cli.domains import backend as backend_domain

    SUBPARSERS["provider"] = provider_domain.add_parser(sub, common)
    SUBPARSERS["model"] = model_domain.add_parser(sub, common)
    SUBPARSERS["settings"] = settings_domain.add_parser(sub, common)
    SUBPARSERS["resource"] = resource_domain.add_parser(sub, common)
    SUBPARSERS["skill"] = skill_domain.add_parser(sub, common)
    SUBPARSERS["mcp"] = mcp_domain.add_parser(sub, common)
    SUBPARSERS["agent"] = agent_domain.add_parser(sub, common)
    SUBPARSERS["backend"] = backend_domain.add_parser(sub, common)

    help_parser = sub.add_parser(
        "help", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="查看帮助（常用模式；--all 查看完整版）",
    )
    add_leveled_help(help_parser)
    help_parser.add_argument(
        "topic", nargs="?",
        choices=["provider", "model", "settings", "resource", "skill", "mcp", "agent", "backend"],
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


def _emit_error(args, kind: str, message: str, code: int) -> int:
    """统一错误输出：--json 时输出机器可读 JSON 至 stderr，否则纯文本。"""
    if getattr(args, "json", False):
        output.print_json({"error": {"type": kind, "message": message, "exit_code": code}})
    else:
        print(f"错误: {message}", file=sys.stderr)
    return code


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
        return _emit_error(args, "usage", str(exc), 2)
    except ResolutionError as exc:
        return _emit_error(args, "resolution", exc.message, 3)
    except ApiError as exc:
        return _emit_error(args, "api", str(exc), 1)
    except KeyboardInterrupt:
        return _emit_error(args, "interrupt", "已取消", 130)


if __name__ == "__main__":
    sys.exit(main())
