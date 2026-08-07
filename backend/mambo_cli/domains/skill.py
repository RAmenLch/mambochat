"""mambo skill — Skill 技能包管理（专用语义操作域）。"""
from __future__ import annotations

import os
import sys

from backend.mambo_cli.client import with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.util import UsageError
from backend.mambo_cli.resolver import (
    build_resource_tree,
    is_directory,
    resolve_resource,
    resource_path_of,
    resource_type_label,
)

SKILL_TYPE = "skill"


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "skill", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="Skill 技能包管理（创建/校验/导入/删除）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="skill_action", metavar="<action>")

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

    lp = cmd("list", "列出全部 Skill")
    lp.set_defaults(func=cmd_list)

    cp = cmd("create", "创建 Skill（自动初始化 SKILL.md）")
    cp.add_argument("--name", required=True, help="Skill 名称（须符合规范）")
    cp.add_argument("--description", required=True, help="Skill 描述")
    cp.add_argument("--into", metavar="DIR", help="目标父目录路径（缺省为资源根）")
    cp.set_defaults(func=cmd_create)

    vp = cmd("validate", "校验 Skill 是否符合 Agent Skills 规范")
    vp.add_argument("path", help="Skill 目录路径")
    vp.set_defaults(func=cmd_validate)

    ip = cmd("import", "导入 Skill（本地文件/ZIP 或 GitHub 仓库）", advanced=True)
    src = ip.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", metavar="PATH", help="本地 SKILL.md 或 ZIP 包路径")
    src.add_argument("--github", metavar="SOURCE",
                     help="GitHub 来源（URL 或 owner/repo，如 https://github.com/owner/skills "
                          "或 owner/skills；本系统等价于 npx skills add owner/repo）")
    ip.add_argument("--into", metavar="DIR", help="导入到哪个目录（缺省为资源根）")
    ip.add_argument("--on-conflict", choices=["error", "overwrite", "skip"], default="error",
                    help="同名冲突处理（默认 error）")
    ip.set_defaults(func=cmd_import)

    dp = cmd("delete", "删除 Skill 目录（递归）")
    dp.add_argument("path", help="Skill 目录路径")
    dp.add_argument("-R", "--recursive", action="store_true", help="递归删除（Skill 为目录型，必填）")
    dp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    dp.set_defaults(func=cmd_delete)

    return p


def _into_id(api, args) -> str | None:
    into = getattr(args, "into", None)
    if not into or into == "/":
        return None
    resources = api.list_resources()
    dest = resolve_resource(resources, into)
    if not is_directory(dest):
        raise UsageError(f"--into '{into}' 不是目录型资源。")
    return dest["id"]


def _skills(resources: list[dict]) -> list[dict]:
    return [r for r in resources if r.get("resourceType") == SKILL_TYPE]


@with_api
def cmd_list(args, api):
    resources = api.list_resources()
    skills = _skills(resources)
    if args.json:
        output.print_json(skills)
        return 0
    if not skills:
        print("（无 Skill）")
        return 0
    by_id = {r["id"]: r for r in resources}
    rows = [{
        "id": s["id"],
        "path": resource_path_of(s["id"], by_id, resources),
        "name": s.get("name"),
        "description": s.get("description") or "",
    } for s in skills]
    output.print_table(rows, [
        ("id", "ID", output.short_id),
        ("path", "PATH", None),
        ("name", "NAME", None),
        ("description", "DESCRIPTION", None),
    ])
    return 0


@with_api
def cmd_create(args, api):
    parent_id = _into_id(api, args)
    created = api.create_skill({
        "name": args.name,
        "description": args.description,
        "parentId": parent_id,
    })
    if args.json:
        output.print_json(created)
    else:
        resources = api.list_resources()
        by_id = {r["id"]: r for r in resources}
        print(f"已创建 Skill: {resource_path_of(created['id'], by_id, resources)}")
    return 0


@with_api
def cmd_validate(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    if target.get("resourceType") != SKILL_TYPE:
        raise UsageError(f"'{args.path}' 不是 Skill 类型资源"
                         f"（{resource_type_label(target)}）。")
    result = api.validate_skill(target["id"])
    if args.json:
        output.print_json(result)
        return 0
    ok = result.get("is_valid")
    print(f"校验结果: {'✅ 通过' if ok else '❌ 未通过'}")
    for err in result.get("errors") or []:
        print(f"  [错误] {err}")
    for warn in result.get("warnings") or []:
        print(f"  [警告] {warn}")
    return 0 if ok else 1


@with_api
def cmd_import(args, api):
    parent_id = _into_id(api, args)
    if args.github:
        result = api.import_skill_github(args.github, parent_id, args.on_conflict)
    else:
        if not os.path.isfile(args.file):
            raise UsageError(f"本地文件不存在: {args.file}")
        with open(args.file, "rb") as f:
            data = f.read()
        result = api.import_skill_file(data, os.path.basename(args.file), parent_id, args.on_conflict)
    if args.json:
        output.print_json(result)
        return 0
    print(f"导入完成: 识别 {result.get('total_detected', 0)} 个 Skill, "
          f"成功 {result.get('success_count', 0)}, 失败 {result.get('failed_count', 0)}, "
          f"跳过 {result.get('skipped_count', 0)}")
    for item in result.get("details") or []:
        mark = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(item.get("status"), "?")
        extra = f"（{item.get('error')}）" if item.get("error") else ""
        print(f"  {mark} {item.get('name')} {extra}")
    return 0 if result.get("failed_count", 0) == 0 else 1


@with_api
def cmd_delete(args, api):
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    if target.get("resourceType") != SKILL_TYPE:
        raise UsageError(f"'{args.path}' 不是 Skill 类型资源"
                         f"（{resource_type_label(target)}）。")
    if not args.recursive:
        raise UsageError(f"'{args.path}' 是 Skill 目录，递归删除需 -R")
    children, _roots, _by_id = build_resource_tree(resources)

    def count_subtree(rid):
        total = 0
        for child in children.get(rid, []):
            total += 1 + count_subtree(child["id"])
        return total

    n = count_subtree(target["id"])
    print(f"将递归删除 Skill '{target['name']}' 及其 {n} 个子项...", file=sys.stderr)
    deleted = api.delete_resource(target["id"])
    if args.json:
        output.print_json(deleted)
    else:
        print(f"已删除 Skill: {target['name']}")
    return 0
