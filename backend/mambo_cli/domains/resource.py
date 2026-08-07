"""mambo resource — 文件系统式资源管理。"""
from __future__ import annotations

import json
import os
import sys

from backend.mambo_cli.client import ApiError, with_api
from backend.mambo_cli.formatter import LeveledHelpFormatter, add_leveled_help, add_arg, mark_advanced
from backend.mambo_cli import output
from backend.mambo_cli.util import UsageError
from backend.mambo_cli.resolver import (
    ResolutionError,
    build_resource_tree,
    is_directory,
    resolve_resource,
    resolve_resource_parent,
    resource_path_of,
    resource_type_label,
)

WRITE_TYPES = {"file": "file", "prompt": "system_prompt", "template": "submessage_template"}
CAT_DEFAULT_MAX_LEN = 2000


def add_parser(subparsers, common):
    p = subparsers.add_parser(
        "resource", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="资源管理（文件系统式: ls/cat/mkdir/update/write/rm/mv/find/upload/version）",
    )
    add_leveled_help(p)
    sp = p.add_subparsers(dest="resource_action", metavar="<action>")

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

    lp = cmd("ls", "列出目录内容（类型标识: [kb]/[skill]/[folder] 与 [file]/[prompt]/[template]）")
    lp.add_argument("path", nargs="?", help="目录路径（绝对路径如 /知识库，缺省列出根目录）")
    lp.set_defaults(func=cmd_ls)

    cp = cmd("cat", "查看文件资源内容（仅文件型；默认截断 2000 字符）")
    cp.add_argument("path", help="文件路径")
    cp.add_argument("--max-len", type=int, default=CAT_DEFAULT_MAX_LEN, metavar="N",
                    help=f"显示前 N 个字符（默认 {CAT_DEFAULT_MAX_LEN}）")
    cp.set_defaults(func=cmd_cat)

    mp = cmd("mkdir", "创建普通文件夹")
    mp.add_argument("path", help="新文件夹路径，如 新目录 或 父目录/新目录")
    mp.set_defaults(func=cmd_mkdir)

    up = cmd("update", "修改资源名称/描述（只更新传入的参数）")
    up.add_argument("path", help="资源路径（绝对路径或短ID）")
    up.add_argument("--name", help="新名称")
    up.add_argument("--description", help="新描述")
    up.set_defaults(func=cmd_update)

    wp = cmd("write", "创建或覆盖文件资源内容（写入即新版本）")
    wp.add_argument("path", help="文件路径（已存在则更新内容，不存在则新建）")
    content_group = wp.add_mutually_exclusive_group(required=True)
    content_group.add_argument("--content", metavar="TEXT", help="直接提供文本内容")
    content_group.add_argument("--file", metavar="LOCAL", help="从本地文件读取内容")
    wp.add_argument("--type", dest="write_type", choices=list(WRITE_TYPES), default="file",
                    help="文件类型（默认 file；prompt=system_prompt, template=submessage_template）")
    add_arg(wp, "--attr", metavar="JSON", advanced=True,
            help="template 类型的属性配置（JSON 字符串，如 '{\"show_tool_mode\": true}'）")
    wp.set_defaults(func=cmd_write)

    rp = cmd("rm", "删除资源（目录需 -R 递归）")
    rp.add_argument("path", help="资源路径")
    rp.add_argument("-R", "--recursive", action="store_true", help="递归删除目录型资源")
    rp.add_argument("--yes", action="store_true", help="确认删除（必填，防误删）")
    rp.set_defaults(func=cmd_rm)

    vp = cmd("mv", "移动资源到目标目录（仅移入语义，不处理排序）")
    vp.add_argument("path", help="要移动的资源路径")
    vp.add_argument("target", help="目标目录路径（/ 表示资源根）")
    vp.set_defaults(func=cmd_mv)

    fp = cmd("find", "搜索资源名称/描述/内容（文本型资源如 prompt/template 可搜内容；文件型资源按名称/描述匹配）")
    fp.add_argument("keyword", help="关键词或正则")
    fp.add_argument("--path", dest="root", metavar="P", help="搜索范围根目录（绝对路径或短ID，缺省全局）")
    fp.add_argument("--regex", action="store_true", help="按正则匹配")
    fp.set_defaults(func=cmd_find)

    up = cmd("upload", "上传本地文件为资源（路径为目录=新建，为文件=更新内容）", advanced=True)
    up.add_argument("local", metavar="LOCAL", help="本地文件路径")
    up.add_argument("path", help="目标路径（目录则新建文件资源，文件则更新其内容）")
    up.set_defaults(func=cmd_upload)

    # ---- version 子命令组 ----
    vgroup = sp.add_parser(
        "version", parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
        help="[高级] 资源版本管理（仅文件型资源）",
    )
    add_leveled_help(vgroup)
    mark_advanced(vgroup)
    vs = vgroup.add_subparsers(dest="version_action", metavar="<action>")

    def vcmd(name, help_text):
        vcp = vs.add_parser(
            name, parents=[common], add_help=False, formatter_class=LeveledHelpFormatter,
            help=help_text,
        )
        add_leveled_help(vcp)
        return vcp

    vl = vcmd("list", "列出资源版本")
    vl.add_argument("path", help="文件型资源路径（绝对路径或短ID）")
    vl.set_defaults(func=cmd_version_list)

    vsa = vcmd("set-active", "将指定版本设为活跃版本")
    vsa.add_argument("path", help="文件型资源路径（绝对路径或短ID）")
    vsa.add_argument("version", help="版本引用（短ID前缀）")
    vsa.set_defaults(func=cmd_version_set_active)

    vd = vcmd("delete", "删除指定版本（不能删除活跃版本）")
    vd.add_argument("path", help="文件型资源路径（绝对路径或短ID）")
    vd.add_argument("version", help="版本引用（短ID前缀）")
    vd.set_defaults(func=cmd_version_delete)

    return p


def _load_local_file(local: str) -> tuple[bytes, str, str]:
    if not os.path.isfile(local):
        raise UsageError(f"本地文件不存在: {local}")
    with open(local, "rb") as f:
        data = f.read()
    from backend.mambo_cli.util import guess_mime
    return data, os.path.basename(local), guess_mime(local)


def _require_file_resource(res, op: str) -> None:
    if is_directory(res):
        raise ResolutionError(f"操作 '{op}' 不适用于目录型资源 '{res.get('name')}'"
                              f"（{resource_type_label(res)}）。")


def _is_text_content(res: dict) -> bool:
    """system_prompt / submessage_template 的 version.content 为文本本身；
    file / kb_file 的 content 为文件 ID。"""
    return res.get("resourceType") in ("system_prompt", "submessage_template")


def _read_content(api, target: dict) -> str:
    version = target.get("latest_version")
    if not version or version.get("content") is None:
        raise ResolutionError(f"资源 '{target.get('name')}' 没有可读内容。")
    if _is_text_content(target):
        return str(version["content"])
    result = api.get_file_content(version["content"])
    return result.get("content") or ""


@with_api
def cmd_ls(args, api):
    resources = api.list_resources()
    children, roots, by_id = build_resource_tree(resources)
    if args.path in ("/", None):
        nodes = roots
    else:
        target = resolve_resource(resources, args.path)
        if is_directory(target):
            nodes = children.get(target["id"], [])
        else:
            nodes = [target]
    if args.json:
        output.print_json(nodes)
        return 0
    if not nodes:
        print("（空）")
        return 0
    rows = [{
        **node,
        "_type": resource_type_label(node),
        "_name_display": (node.get("name") or "") + ("/" if is_directory(node) else ""),
    } for node in nodes]
    output.print_table(rows, [
        ("_type", "TYPE", None),
        ("_name_display", "NAME", None),
        ("description", "DESCRIPTION", None),
        ("updatedAt", "UPDATED", lambda v: (v or "")[:19]),
    ])
    return 0


@with_api
def cmd_cat(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    _require_file_resource(target, "cat")
    content = _read_content(api, target)
    total = len(content)
    truncated = total > args.max_len
    shown = content[: args.max_len]
    if args.json:
        output.print_json({
            "name": target.get("name"),
            "path": resource_path_of(target["id"], {r["id"]: r for r in resources}, resources),
            "content": shown,
            "truncated": truncated,
            "total_length": total,
        })
    else:
        print(shown, end="")
        if truncated:
            print(f"\n...（已截断，共 {total} 字符，显示前 {args.max_len} 字符）")
        else:
            print()
    return 0


@with_api
def cmd_mkdir(args, api):
    resources = api.list_resources()
    parent_id, name = resolve_resource_parent(resources, args.path)
    created = api.create_resource({
        "name": name,
        "itemType": "folder",
        "parentId": parent_id,
    })
    if args.json:
        output.print_json(created)
    else:
        fresh = api.list_resources()
        by_id = {r["id"]: r for r in fresh}
        print(f"已创建文件夹: {resource_path_of(created['id'], by_id, fresh)}")
    return 0


@with_api
def cmd_update(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.description is not None:
        data["description"] = args.description
    if not data:
        raise UsageError("至少提供一个要修改的参数（--name 或 --description）")
    updated = api.update_resource(target["id"], data)
    if args.json:
        output.print_json(updated)
    else:
        fresh = api.list_resources()
        by_id = {r["id"]: r for r in fresh}
        print(f"已更新: {resource_path_of(updated['id'], by_id, fresh)}")
        output.print_kv({k: updated.get(k) for k in ("name", "description")})
    return 0


@with_api
def cmd_write(args, api):
    resources = api.list_resources()
    content = args.content if args.content is not None else _read_local_text(args.file)

    # 已存在 → 更新内容（新版本）；不存在 → 新建文件资源
    existing = None
    try:
        existing = resolve_resource(resources, args.path)
    except ResolutionError:
        pass

    if existing is not None:
        _require_file_resource(existing, "write")
        if _is_text_content(existing):
            # prompt/template: 内容为文本，创建新版本并激活
            version = api.create_resource_version(existing["id"], {
                "name": f"Update {existing.get('name')}",
                "content": content,
            })
            api.set_active_version(existing["id"], version["id"])
            updated = api.get_resource(existing["id"])
        else:
            updated = api.upload_resource_file(
                content.encode("utf-8"), existing.get("name") or "content.txt",
                "application/octet-stream", resource_id=existing["id"],
            )
        if args.json:
            output.print_json(updated)
        else:
            print(f"已更新: {resource_path_of(existing['id'], {r['id']: r for r in resources}, resources)}（新版本已激活）")
        return 0

    # 新建：file 类型先建文件记录；prompt/template 直接以文本作为初始内容
    parent_id, name = resolve_resource_parent(resources, args.path)
    rtype = WRITE_TYPES[args.write_type]
    data = {
        "name": name,
        "itemType": "resource",
        "resourceType": rtype,
        "parentId": parent_id,
    }
    if rtype == "file":
        file_rec = api.upload_file(content.encode("utf-8"), name, "text/plain")
        data["initial_content"] = file_rec["id"]
    else:
        data["initial_content"] = content
    if args.attr:
        try:
            data["initial_attributes"] = json.loads(args.attr)
        except json.JSONDecodeError as exc:
            raise UsageError(f"--attr 不是合法 JSON: {exc}")
    created = api.create_resource(data)
    if args.json:
        output.print_json(created)
    else:
        fresh = api.list_resources()
        by_id = {r["id"]: r for r in fresh}
        print(f"已创建: {resource_path_of(created['id'], by_id, fresh)}"
              f"（类型 {rtype}）")
    return 0


def _read_local_text(local: str) -> str:
    if not os.path.isfile(local):
        raise UsageError(f"本地文件不存在: {local}")
    with open(local, "r", encoding="utf-8") as f:
        return f.read()


def _count_subtree(resource_id: str, children: dict) -> int:
    total = 0
    for child in children.get(resource_id, []):
        total += 1 + _count_subtree(child["id"], children)
    return total


@with_api
def cmd_rm(args, api):
    if args.path == "/":
        raise UsageError("不能删除资源根目录。")
    if not args.yes:
        raise UsageError("删除操作需要 --yes 确认（防止误删）")
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    if is_directory(target):
        if not args.recursive:
            raise UsageError(f"'{args.path}' 是目录型资源"
                             f"（{resource_type_label(target)}），递归删除需 -R")
        children, _roots, _by_id = build_resource_tree(resources)
        count = _count_subtree(target["id"], children)
        print(f"将递归删除目录 {target['name']} 及其 {count} 个子项...", file=sys.stderr)
    deleted = api.delete_resource(target["id"])
    if args.json:
        output.print_json(deleted)
    else:
        print(f"已删除: {target['name']}（{resource_type_label(target)}）")
    return 0


@with_api
def cmd_mv(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    if args.target == "/":
        reference_id = "root"  # 后端约定 reference_id="root" 表示资源根
    else:
        dest = resolve_resource(resources, args.target)
        if not is_directory(dest):
            raise UsageError(f"目标 '{args.target}' 不是目录型资源。")
        reference_id = dest["id"]
    api.move_resources([target["id"]], reference_id, action="inside")
    if args.json:
        output.print_json({"message": "Move successful", "moved": target["name"], "into": args.target})
    else:
        print(f"已移动: {target['name']} → {args.target}")
    return 0


@with_api
def cmd_find(args, api):
    root_id = None
    if args.root and args.root != "/":
        resources = api.list_resources()
        root = resolve_resource(resources, args.root)
        root_id = root["id"]
    result = api.search_resources(args.keyword, root_id=root_id, enable_regex=args.regex)
    items = result.get("items") or []
    if args.json:
        output.print_json(result)
        return 0
    if not items:
        print(f"未找到匹配 '{args.keyword}' 的资源。")
        print("提示: 文件型资源（file）的内容存储于独立文件，不参与内容检索；"
              "可改用 mambo resource ls / cat 逐项查看。", file=sys.stderr)
        return 0
    resources = api.list_resources()
    by_id = {r["id"]: r for r in resources}
    rows = [{
        "path": resource_path_of(i["resource_id"], by_id, resources),
        "resource_name": (i.get("resource_name") or "")
                         + ("/" if is_directory(by_id.get(i["resource_id"], {})) else ""),
        "match_type": i.get("match_type"),
        "context_text": i.get("context_text", ""),
    } for i in items]
    output.print_table(rows, [
        ("path", "PATH", None),
        ("resource_name", "NAME", None),
        ("match_type", "MATCH", None),
        ("context_text", "CONTEXT", None),
    ])
    print(f"共 {result.get('total', 0)} 条匹配。")
    return 0


@with_api
def cmd_upload(args, api):
    resources = api.list_resources()
    data, filename, mime = _load_local_file(args.local)

    def upload_new(path_display: str, parent_id: str | None):
        try:
            return api.upload_resource_file(data, filename, mime, parent_id=parent_id)
        except ApiError as exc:
            if exc.status_code == 400 and "already exists" in str(exc.detail):
                target = f"/{filename}" if path_display == "/" \
                    else f"{path_display.rstrip('/')}/{filename}"
                raise UsageError(
                    f"目标目录下已存在同名资源 '{filename}'。\n"
                    f"覆盖需明确指向该文件: mambo resource upload <本地文件> {target}"
                )
            raise

    if args.path == "/":
        # 根目录下新建（文件名用本地文件名）；后端以 parent_id="root" 表示根
        created = upload_new("/", "root")
    else:
        try:
            existing = resolve_resource(resources, args.path)
        except ResolutionError:
            raise UsageError(
                f"路径 '{args.path}' 未找到。upload 目标须为已存在的目录（新建文件）"
                f"或文件（更新内容），如 / 或 /目录名。"
            )
        if is_directory(existing):
            created = upload_new(args.path, existing["id"])
        else:
            updated = api.upload_resource_file(data, filename, mime, resource_id=existing["id"])
            if args.json:
                output.print_json(updated)
            else:
                print(f"已更新内容: {args.path}（新版本已激活）")
            return 0
    if args.json:
        output.print_json(created)
    else:
        fresh = api.list_resources()
        by_id = {r["id"]: r for r in fresh}
        print(f"已上传: {resource_path_of(created['id'], by_id, fresh)}")
    return 0


def _resolve_version(target: dict, version_ref: str) -> dict:
    versions = target.get("versions") or []
    matches = [v for v in versions if v["id"].startswith(version_ref)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResolutionError(f"版本引用 '{version_ref}' 匹配到多个版本: "
                              + ", ".join(v["id"][:8] for v in matches))
    raise ResolutionError(f"版本引用 '{version_ref}' 未找到。可用 mambo resource version list 查看。")


@with_api
def cmd_version_list(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    _require_file_resource(target, "version list")
    detail = api.get_resource(target["id"])
    versions = detail.get("versions") or []
    active_id = detail.get("latestVersionId")
    if args.json:
        output.print_json(versions)
        return 0
    if not versions:
        print("（无版本）")
        return 0
    rows = [{
        "id": v["id"],
        "name": v.get("name"),
        "commitMessage": v.get("commitMessage") or "",
        "active": "yes" if v["id"] == active_id else "",
        "createdAt": (v.get("createdAt") or "")[:19],
    } for v in versions]
    output.print_table(rows, [
        ("id", "ID", output.short_id),
        ("name", "NAME", None),
        ("commitMessage", "COMMIT", None),
        ("active", "ACTIVE", None),
        ("createdAt", "CREATED", None),
    ])
    return 0


@with_api
def cmd_version_set_active(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    _require_file_resource(target, "version set-active")
    detail = api.get_resource(target["id"])
    version = _resolve_version(detail, args.version)
    updated = api.set_active_version(target["id"], version["id"])
    if args.json:
        output.print_json(updated)
    else:
        print(f"已激活版本 {version['id'][:8]}（{version.get('name')}）→ {args.path}")
    return 0


@with_api
def cmd_version_delete(args, api):
    resources = api.list_resources()
    target = resolve_resource(resources, args.path)
    _require_file_resource(target, "version delete")
    detail = api.get_resource(target["id"])
    version = _resolve_version(detail, args.version)
    api.delete_resource_version(version["id"])
    if args.json:
        output.print_json({"message": "Version deleted successfully"})
    else:
        print(f"已删除版本 {version['id'][:8]}（{version.get('name')}）")
    return 0
