# MamboChat API Backend Client
#
# WebSocket client that connects to MamboChat server and provides
# filesystem access. The client does NOT expose any HTTP interface.
#
# Usage:
#   python main.py --server-url ws://localhost:8000 --backend-id <uuid> --api-key <key> --root-dir /your/project

import argparse
import asyncio
import base64
import fnmatch
import json
import logging
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import websockets
from websockets.asyncio.client import ClientConnection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mambochat-client")


# ==========================================
# Configuration
# ==========================================
class ClientConfig:
    def __init__(
        self,
        server_url: str,
        backend_id: str,
        api_key: str,
        root_dir: str = ".",
        edit_whitelist: Optional[list[str]] = None,
        edit_blacklist: Optional[list[str]] = None,
        ignore_dirs: Optional[list[str]] = None,
        reconnect_interval: float = 5.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.backend_id = backend_id
        self.api_key = api_key
        self.root_dir = os.path.abspath(root_dir)
        self.edit_whitelist = edit_whitelist or []
        self.edit_blacklist = edit_blacklist or []
        self.ignore_dirs = ignore_dirs or [
            '.git', 'node_modules', '__pycache__', '.venv', 'target', 'build', 'dist'
        ]
        self.reconnect_interval = reconnect_interval


config: ClientConfig = ClientConfig(
    server_url="",
    backend_id="",
    api_key="",
)


# ==========================================
# Filesystem Service
# ==========================================
def _resolve_path(requested_path: str) -> str:
    """Resolve a requested path relative to root_dir, preventing traversal."""
    if not requested_path:
        requested_path = "/"
    if not requested_path.startswith("/"):
        requested_path = "/" + requested_path

    parts = []
    for segment in requested_path.split("/"):
        if segment == ".." or segment == "." or not segment:
            continue
        parts.append(segment)

    resolved = os.path.join(config.root_dir, *parts)
    resolved = os.path.normpath(resolved)
    if not resolved.startswith(config.root_dir):
        raise ValueError(f"Path traversal not allowed: {requested_path}")
    return resolved


def _check_edit_permission(file_path: str) -> None:
    filename = os.path.basename(file_path)
    if config.edit_whitelist and not any(fnmatch.fnmatch(filename, p) for p in config.edit_whitelist):
        raise PermissionError(f"Edit denied: '{filename}' not in whitelist")
    if config.edit_blacklist and any(fnmatch.fnmatch(filename, p) for p in config.edit_blacklist):
        raise PermissionError(f"Edit denied: '{filename}' in blacklist")


def _should_ignore_dir(dirname: str) -> bool:
    return dirname in config.ignore_dirs


def _walk_dir(directory: str, max_depth: int = -1, current_depth: int = 1):
    """Yield (filepath, is_dir, is_unexpanded) tuples."""
    try:
        entries = sorted(os.listdir(directory))
    except PermissionError:
        return

    for entry in entries:
        full_path = os.path.join(directory, entry)
        is_dir = os.path.isdir(full_path)

        is_unexpanded = False
        if is_dir:
            if _should_ignore_dir(entry):
                is_unexpanded = True
            elif max_depth != -1 and current_depth >= max_depth:
                is_unexpanded = True

        yield full_path, is_dir, is_unexpanded

        if is_dir and not is_unexpanded:
            yield from _walk_dir(full_path, max_depth, current_depth + 1)


# ==========================================
# File Operation Handlers
# ==========================================
def handle_tree(path: str, depth: int = 3) -> dict:
    try:
        base = _resolve_path(path)
    except ValueError:
        return {"tree": f"Error: Invalid path {path}"}

    if not os.path.isdir(base):
        return {"tree": f"Error: Not a directory: {path}"}

    tree_dict: dict[str, Any] = {}
    for filepath, is_dir, is_unexpanded in _walk_dir(base, max_depth=depth):
        rel = os.path.relpath(filepath, base)
        parts = rel.replace("\\", "/").split("/")
        current = tree_dict
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        if is_dir:
            current[parts[-1]] = "__UNEXPANDED__" if is_unexpanded else {}
        else:
            current[parts[-1]] = None

    if not tree_dict:
        return {"tree": f"No files found in {path}"}

    lines = [path]

    def _format(node: dict, current_depth: int):
        indent = "  " * current_depth
        sorted_items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))
        for k, v in sorted_items:
            if v is None:
                lines.append(f"{indent}{k}")
            elif v == "__UNEXPANDED__":
                lines.append(f"{indent}{k}/ ... (unexpanded)")
            else:
                if not v:
                    lines.append(f"{indent}{k}/ (empty)")
                else:
                    curr_k = k
                    curr_v = v
                    while isinstance(curr_v, dict) and len(curr_v) == 1:
                        only_key = list(curr_v.keys())[0]
                        if curr_v[only_key] is None or curr_v[only_key] == "__UNEXPANDED__":
                            break
                        curr_k = f"{curr_k}/{only_key}"
                        curr_v = curr_v[only_key]
                    lines.append(f"{indent}{curr_k}/")
                    if isinstance(curr_v, dict):
                        _format(curr_v, current_depth + 1)

    _format(tree_dict, 1)
    result = "\n".join(lines)
    if len(result) > 16000:
        result = result[:16000] + "\n... (tree truncated)"
    return {"tree": result}


def handle_ls(path: str) -> dict:
    try:
        physical = _resolve_path(path)
    except ValueError:
        return {"items": []}

    if not os.path.isdir(physical):
        return {"items": []}

    results = []
    try:
        for entry in sorted(os.listdir(physical)):
            full = os.path.join(physical, entry)
            is_dir = os.path.isdir(full)
            stat = os.stat(full)
            vpath = (path.rstrip("/") + "/" + entry) if path else "/" + entry
            if is_dir:
                vpath += "/"
            results.append({
                "path": vpath,
                "is_dir": is_dir,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    except PermissionError:
        pass
    return {"items": results}


def handle_read_file(path: str, offset: int = 0, limit: int = 2000) -> dict:
    try:
        physical = _resolve_path(path)
    except ValueError as e:
        return {"error": str(e)}

    if not os.path.isfile(physical):
        return {"error": f"File not found: {path}"}

    try:
        with open(physical, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        return {"error": f"File '{path}' is not a valid UTF-8 text file."}

    if not content.strip():
        return {"content": "", "lines": [], "total_lines": 0}

    lines = content.splitlines()
    start = offset
    end = min(start + limit, len(lines))

    if start >= len(lines):
        return {"error": f"Line offset {offset} exceeds file length ({len(lines)} lines)"}

    selected = lines[start:end]
    numbered_lines = [f"{i + start + 1}|{line}" for i, line in enumerate(selected)]

    return {
        "content": content,
        "lines": numbered_lines,
        "total_lines": len(lines),
        "offset": start,
        "limit": limit,
    }


def handle_write_file(path: str, content: str) -> dict:
    try:
        _check_edit_permission(path)
        physical = _resolve_path(path)
    except (ValueError, PermissionError) as e:
        return {"error": str(e)}

    if os.path.exists(physical):
        return {"error": f"File already exists: {path}"}

    try:
        os.makedirs(os.path.dirname(physical), exist_ok=True)
        with open(physical, "w", encoding="utf-8") as f:
            f.write(content)
        return {"path": path, "success": True}
    except Exception as e:
        return {"error": str(e)}


def handle_edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    try:
        _check_edit_permission(path)
        physical = _resolve_path(path)
    except (ValueError, PermissionError) as e:
        return {"error": str(e)}

    if not os.path.isfile(physical):
        return {"error": f"File not found: {path}"}

    try:
        with open(physical, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"error": str(e)}

    if old_string not in content:
        return {"error": "old_string not found in file"}

    if replace_all:
        occurrences = content.count(old_string)
        new_content = content.replace(old_string, new_string)
    else:
        idx = content.index(old_string)
        new_content = content[:idx] + new_string + content[idx + len(old_string):]
        occurrences = 1

    try:
        with open(physical, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"path": path, "occurrences": occurrences, "success": True}
    except Exception as e:
        return {"error": str(e)}


def handle_grep_files(pattern: str, path: str, glob: Optional[str] = None) -> dict:
    try:
        base = _resolve_path(path)
    except ValueError:
        return {"matches": []}

    matches = []
    max_file_size = 10 * 1024 * 1024

    if os.path.isfile(base):
        if glob:
            filename = os.path.basename(base)
            if not fnmatch.fnmatch(filename, glob):
                return {"matches": matches}
        if os.path.getsize(base) > max_file_size:
            return {"matches": matches}
        try:
            with open(base, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if pattern in line:
                        matches.append({
                            "path": path,
                            "line": line_num,
                            "text": line.rstrip("\n"),
                        })
        except (UnicodeDecodeError, PermissionError):
            pass
        return {"matches": matches}

    if not os.path.isdir(base):
        return {"matches": []}

    for filepath, is_dir, _ in _walk_dir(base):
        if is_dir:
            continue
        if glob:
            filename = os.path.basename(filepath)
            if not fnmatch.fnmatch(filename, glob):
                continue
        try:
            size = os.path.getsize(filepath)
            if size > max_file_size:
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if pattern in line:
                        vpath = "/" + os.path.relpath(filepath, config.root_dir).replace("\\", "/")
                        matches.append({
                            "path": vpath,
                            "line": line_num,
                            "text": line.rstrip("\n"),
                        })
        except (UnicodeDecodeError, PermissionError):
            continue

    return {"matches": matches}


def handle_glob_files(pattern: str, path: str) -> dict:
    try:
        base = _resolve_path(path)
    except ValueError:
        return {"items": []}

    if not os.path.isdir(base):
        return {"items": []}

    results = []
    effective_pattern = pattern.lstrip("/")

    for filepath, is_dir, _ in _walk_dir(base):
        if is_dir:
            continue
        rel = os.path.relpath(filepath, base).replace("\\", "/")
        if fnmatch.fnmatch(rel, effective_pattern):
            try:
                stat = os.stat(filepath)
                vpath = "/" + os.path.relpath(filepath, config.root_dir).replace("\\", "/")
                results.append({
                    "path": vpath,
                    "is_dir": False,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
            except OSError:
                pass

    results.sort(key=lambda x: x["path"])
    return {"items": results}


def handle_upload_files(files: list[dict]) -> dict:
    results = []
    for item in files:
        path = item.get("path", "")
        try:
            _check_edit_permission(path)
            physical = _resolve_path(path)
            content = base64.b64decode(item.get("content_b64", ""))
            os.makedirs(os.path.dirname(physical), exist_ok=True)
            with open(physical, "wb") as f:
                f.write(content)
            results.append({"path": path, "error": None})
        except (ValueError, PermissionError) as e:
            results.append({"path": path, "error": str(e)})
        except Exception as e:
            results.append({"path": path, "error": str(e)})
    return {"results": results}


def handle_download_files(paths: list[str]) -> dict:
    results = []
    for path in paths:
        try:
            physical = _resolve_path(path)
            if not os.path.isfile(physical):
                results.append({"path": path, "error": "file_not_found"})
                continue
            with open(physical, "rb") as f:
                content = f.read()
            results.append({
                "path": path,
                "content_b64": base64.b64encode(content).decode("ascii"),
                "error": None,
            })
        except Exception as e:
            results.append({"path": path, "error": str(e)})
    return {"results": results}


# ==========================================
# Command Dispatcher
# ==========================================
async def handle_command(method: str, params: dict) -> dict:
    """Dispatch a command from the server and return the result."""
    try:
        if method == "tree":
            return handle_tree(params.get("path", "/"), params.get("depth", 3))
        elif method == "ls":
            return handle_ls(params.get("path", "/"))
        elif method == "read_file":
            return handle_read_file(
                params.get("path", "/"),
                params.get("offset", 0),
                params.get("limit", 2000),
            )
        elif method == "write_file":
            return handle_write_file(params.get("path", ""), params.get("content", ""))
        elif method == "edit_file":
            return handle_edit_file(
                params.get("path", ""),
                params.get("old_string", ""),
                params.get("new_string", ""),
                params.get("replace_all", False),
            )
        elif method == "grep_files":
            return handle_grep_files(
                params.get("pattern", ""),
                params.get("path", "/"),
                params.get("glob"),
            )
        elif method == "glob_files":
            return handle_glob_files(params.get("pattern", ""), params.get("path", "/"))
        elif method == "upload_files":
            return handle_upload_files(params.get("files", []))
        elif method == "download_files":
            return handle_download_files(params.get("paths", []))
        else:
            return {"error": f"Unknown method: {method}"}
    except Exception as e:
        logger.exception("Error handling command %s: %s", method, e)
        return {"error": str(e)}


# ==========================================
# WebSocket Client Loop
# ==========================================
async def run_client():
    """Main client loop: connect to server WebSocket, process commands."""
    ws_url = (
        f"{config.server_url}/api/api-client/ws/{config.backend_id}"
        f"?api_key={config.api_key}"
    )

    while True:
        logger.info("Connecting to %s ...", config.server_url)
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info("Connected successfully!")

                # Send client info
                await ws.send(json.dumps({
                    "type": "register_info",
                    "info": {
                        "root_dir": config.root_dir,
                        "hostname": platform.node(),
                        "platform": platform.platform(),
                        "pid": os.getpid(),
                    }
                }))

                # Main message loop
                async for message in ws:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "welcome":
                            logger.info("Server: %s", data.get("message", ""))

                        elif msg_type == "command":
                            request_id = data.get("request_id", "")
                            method = data.get("method", "")
                            params = data.get("params", {})

                            logger.debug("Command: %s %s", method, params)

                            try:
                                result = await handle_command(method, params)
                                await ws.send(json.dumps({
                                    "type": "response",
                                    "request_id": request_id,
                                    "result": result,
                                }))
                            except Exception as e:
                                logger.exception("Command error: %s %s", method, e)
                                await ws.send(json.dumps({
                                    "type": "error",
                                    "request_id": request_id,
                                    "message": str(e),
                                }))

                        else:
                            logger.warning("Unknown message type: %s", msg_type)

                    except json.JSONDecodeError:
                        logger.error("Invalid JSON received from server")
                    except Exception as e:
                        logger.exception("Error processing message: %s", e)

        except websockets.InvalidStatusCode as e:
            if e.status_code == 4003:
                logger.error("Authentication failed! Check your backend_id and api_key.")
                return
            else:
                logger.error("Server returned status %s: %s", e.status_code, e)
        except websockets.ConnectionClosed as e:
            logger.warning("Connection closed (code=%s, reason=%s)", e.code, e.reason)
        except Exception as e:
            logger.error("Connection error: %s", e)

        # Reconnect after interval
        logger.info("Reconnecting in %.0f seconds ...", config.reconnect_interval)
        await asyncio.sleep(config.reconnect_interval)


# ==========================================
# Main
# ==========================================
def parse_args():
    parser = argparse.ArgumentParser(description="MamboChat API Backend Client (WebSocket)")
    parser.add_argument("--server-url", required=True,
                        help="MamboChat server WebSocket URL, e.g. ws://localhost:8000")
    parser.add_argument("--backend-id", required=True,
                        help="Backend ID (uuid) from MamboChat backend config")
    parser.add_argument("--api-key", required=True,
                        help="API key for authentication")
    parser.add_argument("--root-dir", default=".",
                        help="Root directory to expose (default: .)")
    parser.add_argument("--edit-whitelist", default=None,
                        help="Comma-separated edit whitelist patterns")
    parser.add_argument("--edit-blacklist", default=None,
                        help="Comma-separated edit blacklist patterns")
    parser.add_argument("--ignore-dirs", default=None,
                        help="Comma-separated directories to ignore")
    parser.add_argument("--reconnect-interval", type=float, default=5.0,
                        help="Seconds between reconnection attempts (default: 5)")
    return parser.parse_args()


def main():
    global config

    args = parse_args()

    edit_whitelist = [x.strip() for x in args.edit_whitelist.split(",") if x.strip()] if args.edit_whitelist else None
    edit_blacklist = [x.strip() for x in args.edit_blacklist.split(",") if x.strip()] if args.edit_blacklist else None
    ignore_dirs = [x.strip() for x in args.ignore_dirs.split(",") if x.strip()] if args.ignore_dirs else None

    config = ClientConfig(
        server_url=args.server_url,
        backend_id=args.backend_id,
        api_key=args.api_key,
        root_dir=args.root_dir,
        edit_whitelist=edit_whitelist,
        edit_blacklist=edit_blacklist,
        ignore_dirs=ignore_dirs,
        reconnect_interval=args.reconnect_interval,
    )

    print("=" * 60)
    print("  MamboChat API Backend Client (WebSocket)")
    print("=" * 60)
    print(f"  Server URL     : {config.server_url}")
    print(f"  Backend ID     : {config.backend_id}")
    print(f"  Root Directory : {config.root_dir}")
    print(f"  Platform       : {platform.platform()}")
    print("=" * 60)

    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("\nClient stopped.")


if __name__ == "__main__":
    # API_BACKEND 客户端，通过 WebSocket 连接 MamboChat 服务器，提供文件系统访问功能。客户端不暴露任何 HTTP 接口。
    main()
