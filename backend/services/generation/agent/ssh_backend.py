# backend/services/generation/agent/ssh_backend.py

"""Pure SFTP Backend for DeepAgents.

Provides remote filesystem access via SFTP protocol.
File read/write/edit operations use pure SFTP for safety and cross-platform compatibility.
Search operations (grep, glob) prefer native remote commands (grep, rg, find) via SSH
for performance, falling back to pure Python SFTP scanning only when unavailable.
"""

import base64
import fnmatch
import json
import logging
import posixpath
import shlex
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paramiko
import wcmatch.glob as wcglob

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)
from deepagents.backends.utils import (
    _get_file_type,
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

from backend.services.generation.agent.tree_extension import TreeBackendProtocol

logger = logging.getLogger(__name__)


class PureSFTPBackend(SandboxBackendProtocol, TreeBackendProtocol):
    """Backend that reads and writes files on a remote server using ONLY SFTP.

    Also supports shell command execution via SSH.

    Note on Async: This class relies on `BackendProtocol`'s default `asyncio.to_thread`
    wrappers for all `a*` methods (e.g., `aread`, `awrite`). Since `paramiko` is a
    synchronous blocking library, delegating to threads is the correct approach to
    prevent blocking the async event loop.
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str | None = None,
        key_filename: str | None = None,
        port: int = 22,
        root_dir: str = "/",
        edit_whitelist: list[str] | None = None,
        edit_blacklist: list[str] | None = None,
        ignore_dirs: list[str] | None = None,
        max_file_size_mb: int = 10,
    ) -> None:
        """Initialize the pure SFTP backend.

        Args:
            hostname: Remote server hostname or IP.
            username: SSH username.
            password: SSH password (optional if using key).
            key_filename: Path to SSH private key.
            port: SSH port (default 22).
            root_dir: The physical directory on the remote server that acts as the root.
            edit_whitelist: List of glob patterns for allowed edits (e.g., ["*.py"]).
            edit_blacklist: List of glob patterns for forbidden edits.
            ignore_dirs: List of directory names to skip during recursive SFTP walk
                (e.g., node_modules, .git). Defaults to common heavy directories.
            max_file_size_mb: Max file size to read into memory for grep operations.
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.port = port
        self.root_dir = posixpath.normpath(root_dir)
        self.edit_whitelist = edit_whitelist or []
        self.edit_blacklist = edit_blacklist or []

        if ignore_dirs is None:
            self.ignore_dirs = ['.git', 'node_modules', '__pycache__', '.venv', 'target', 'build', 'dist']
        else:
            self.ignore_dirs = ignore_dirs

        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        self._ssh_client: paramiko.SSHClient | None = None
        self._sftp_client: paramiko.SFTPClient | None = None
        self._lock = threading.Lock()
        # Cache for remote command availability
        self._remote_rg_available: bool | None = None
        self._remote_grep_available: bool | None = None
        self._remote_find_available: bool | None = None

    def _connect(self) -> None:
        """Establish SSH and SFTP connections if not already connected.

        Uses double-check locking to prevent race conditions when multiple
        threads (e.g. from ``asyncio.gather`` tool calls) attempt to connect
        simultaneously.
        """
        # Fast path: connection already alive, no lock needed
        if self._ssh_client is not None:
            transport = self._ssh_client.get_transport()
            if transport is not None and transport.is_active():
                return

        with self._lock:
            # Double-check after acquiring lock
            if self._ssh_client is not None:
                transport = self._ssh_client.get_transport()
                if transport is not None and transport.is_active():
                    return

            # Close any stale connection before creating a new one
            if self._sftp_client is not None:
                try:
                    self._sftp_client.close()
                except Exception:
                    pass
                self._sftp_client = None
            if self._ssh_client is not None:
                try:
                    self._ssh_client.close()
                except Exception:
                    pass
                self._ssh_client = None

            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict[str, Any] = {
                "hostname": self.hostname,
                "port": self.port,
                "username": self.username,
                "timeout": 15,
            }
            if self.key_filename:
                connect_kwargs["key_filename"] = self.key_filename
            elif self.password:
                connect_kwargs["password"] = self.password

            logger.debug("Connecting via SFTP to %s@%s:%s", self.username, self.hostname, self.port)
            self._ssh_client.connect(**connect_kwargs)
            self._sftp_client = self._ssh_client.open_sftp()

    @property
    def id(self) -> str:
        """Unique identifier for the sandbox backend instance."""
        return f"ssh://{self.username}@{self.hostname}:{self.port}"

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command on the remote server via SSH.

        Args:
            command: Full shell command string to execute.
            timeout: Maximum time in seconds to wait for the command to complete.

        Returns:
            ExecuteResponse with combined output, exit code, and truncation flag.
        """
        self._connect()
        assert self._ssh_client is not None
        timeout = timeout or 120
        _, stdout_ch, stderr_ch = self._ssh_client.exec_command(command, timeout=timeout)
        exit_code = stdout_ch.channel.recv_exit_status()
        out = stdout_ch.read().decode("utf-8", errors="replace")
        err = stderr_ch.read().decode("utf-8", errors="replace")
        combined = out + err if err else out

        truncated = len(combined) > 100000
        if truncated:
            combined = combined[:100000] + "\n... (output truncated)"

        return ExecuteResponse(output=combined, exit_code=exit_code, truncated=truncated)

    def close(self) -> None:
        """Close connections (thread-safe)."""
        with self._lock:
            if self._sftp_client:
                try:
                    self._sftp_client.close()
                except Exception:
                    pass
                self._sftp_client = None
            if self._ssh_client:
                try:
                    self._ssh_client.close()
                except Exception:
                    pass
                self._ssh_client = None

    def __del__(self) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Remote command helpers
    # ------------------------------------------------------------------
    def _exec_remote(
        self,
        cmd: str,
        timeout: float = 30,
    ) -> tuple[int, str, str]:
        """Execute a command on the remote server via SSH.

        Returns:
            (exit_code, stdout, stderr)
        """
        self._connect()
        assert self._ssh_client is not None
        _, stdout, stderr = self._ssh_client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

    def _check_remote_command(self, cmd: str, attr_name: str) -> bool:
        """Check if a command is available on the remote server (cached)."""
        cached = getattr(self, attr_name, None)
        if cached is not None:
            return cached
        code, _, _ = self._exec_remote(f"command -v {cmd}", timeout=5)
        available = code == 0
        setattr(self, attr_name, available)
        return available

    def _resolve_path(self, virtual_path: str) -> str:
        if not virtual_path.startswith("/"):
            virtual_path = "/" + virtual_path
        norm_vpath = posixpath.normpath(virtual_path)
        if norm_vpath.startswith(".."):
            raise ValueError("Path traversal not allowed.")
        rel_path = norm_vpath.lstrip("/")
        return posixpath.join(self.root_dir, rel_path)

    def _to_virtual_path(self, physical_path: str) -> str:
        if physical_path.startswith(self.root_dir):
            rel = physical_path[len(self.root_dir):]
            if not rel.startswith("/"):
                rel = "/" + rel
            return rel
        return physical_path

    def _check_edit_permission(self, virtual_path: str) -> None:
        filename = posixpath.basename(virtual_path)
        if self.edit_whitelist and not any(fnmatch.fnmatch(filename, p) for p in self.edit_whitelist):
            raise PermissionError(f"Edit denied: File '{filename}' is not in the edit whitelist.")
        if self.edit_blacklist and any(fnmatch.fnmatch(filename, p) for p in self.edit_blacklist):
            raise PermissionError(f"Edit denied: File '{filename}' is in the edit blacklist.")

    def _sftp_mkdir_p(self, remote_directory: str) -> None:
        """Pure SFTP implementation of `mkdir -p`."""
        if remote_directory == '/' or not remote_directory:
            return
        assert self._sftp_client is not None
        try:
            self._sftp_client.stat(remote_directory)
        except IOError:
            self._sftp_mkdir_p(posixpath.dirname(remote_directory))
            try:
                self._sftp_client.mkdir(remote_directory)
            except IOError:
                pass

    def _sftp_walk(self, remotedir: str, current_depth: int = 1, max_depth: int = -1):
        """Pure SFTP recursive directory walker with depth limit.

        Yields: (physical_path, SFTPAttributes, is_unexpanded)
        """
        assert self._sftp_client is not None
        try:
            attrs = self._sftp_client.listdir_attr(remotedir)
        except IOError:
            return

        for attr in attrs:
            filepath = posixpath.join(remotedir, attr.filename)
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False

            is_unexpanded = False
            if is_dir:
                if attr.filename in self.ignore_dirs:
                    is_unexpanded = True
                elif max_depth != -1 and current_depth >= max_depth:
                    is_unexpanded = True

            yield filepath, attr, is_unexpanded

            if is_dir and not is_unexpanded:
                yield from self._sftp_walk(filepath, current_depth + 1, max_depth)

    def tree(self, path: str = "/", depth: int = 3) -> str:
        """Get a compact directory tree structure for LLM context."""
        self._connect()
        try:
            base_physical = self._resolve_path(path)
        except ValueError:
            return f"Error: Invalid path {path}"

        tree_dict = {}
        for filepath, attr, is_unexpanded in self._sftp_walk(base_physical, current_depth=1, max_depth=depth):
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            rel_path = filepath[len(base_physical):].lstrip("/")
            if not rel_path:
                continue

            parts = rel_path.split("/")
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
            return f"No files found in {path}"

        lines = [f"{path}"]

        def _format_tree(node, current_depth):
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
                            _format_tree(curr_v, current_depth + 1)

        _format_tree(tree_dict, 1)

        result = "\n".join(lines)
        if len(result) > 16000:
            return result[:16000] + "\n... (tree truncated due to size)"
        return result

    def ls_info(self, path: str) -> list[FileInfo]:
        self._connect()
        physical_path = self._resolve_path(path)
        try:
            assert self._sftp_client is not None
            attrs = self._sftp_client.listdir_attr(physical_path)
        except IOError:
            return []

        results: list[FileInfo] = []
        for attr in attrs:
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            vpath = posixpath.join(path, attr.filename)
            if is_dir:
                vpath += "/"
            mtime = attr.st_mtime or 0
            results.append({
                "path": vpath,
                "is_dir": is_dir,
                "size": attr.st_size or 0,
                "modified_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat()
            })
        results.sort(key=lambda x: x.get("path", ""))
        return results

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """Read file content, returning base64-encoded data for binary files.

        Args:
            file_path: Absolute virtual path to read.
            offset: Line offset for text files (0-indexed). Ignored for binary.
            limit: Max number of lines for text files. Ignored for binary.

        Returns:
            ReadResult with file_data on success, or error on failure.
            Binary files (image, audio, video, pdf, etc.) return base64
            content with ``encoding="base64"`` for the middleware to construct
            multimodal content blocks for the AI model.
        """
        self._connect()
        physical_path = self._resolve_path(file_path)
        try:
            assert self._sftp_client is not None

            file_type = _get_file_type(file_path)

            if file_type != "text":
                with self._sftp_client.open(physical_path, 'rb') as f:
                    raw = f.read()
                encoded = base64.standard_b64encode(raw).decode("ascii")
                return ReadResult(file_data=FileData(content=encoded, encoding="base64"))

            with self._sftp_client.open(physical_path, 'r') as f:
                content = f.read().decode('utf-8')

            empty_msg = check_empty_content(content)
            if empty_msg:
                return ReadResult(file_data=FileData(content=empty_msg, encoding="utf-8"))

            lines = content.splitlines()
            start_idx = offset
            end_idx = min(start_idx + limit, len(lines))

            if start_idx >= len(lines):
                return ReadResult(error=f"Line offset {offset} exceeds file length ({len(lines)} lines)")

            selected_lines = lines[start_idx:end_idx]
            return ReadResult(
                file_data=FileData(content="\n".join(selected_lines), encoding="utf-8"),
            )
        except IOError as e:
            return ReadResult(error=f"Error reading file '{file_path}': {e}")
        except UnicodeDecodeError:
            return ReadResult(error=f"Error: File '{file_path}' is not a valid UTF-8 text file.")

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            self._check_edit_permission(file_path)
            self._connect()
            physical_path = self._resolve_path(file_path)
            assert self._sftp_client is not None

            try:
                self._sftp_client.stat(physical_path)
                return WriteResult(error=f"Cannot write to {file_path} because it already exists. Read and then make an edit, or write to a new path.")
            except IOError:
                pass

            parent_dir = posixpath.dirname(physical_path)
            self._sftp_mkdir_p(parent_dir)

            with self._sftp_client.open(physical_path, 'w') as f:
                f.write(content)
            return WriteResult(path=file_path, files_update=None)
        except PermissionError as e:
            return WriteResult(error=str(e))
        except Exception as e:
            return WriteResult(error=f"Error writing file '{file_path}': {e}")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        try:
            self._check_edit_permission(file_path)
            self._connect()
            physical_path = self._resolve_path(file_path)
            assert self._sftp_client is not None

            try:
                with self._sftp_client.open(physical_path, 'r') as f:
                    content = f.read().decode('utf-8')
            except IOError:
                return EditResult(error=f"Error: File '{file_path}' not found")

            result = perform_string_replacement(content, old_string, new_string, replace_all)
            if isinstance(result, str):
                return EditResult(error=result)

            new_content, occurrences = result
            with self._sftp_client.open(physical_path, 'w') as f:
                f.write(new_content)
            return EditResult(path=file_path, files_update=None, occurrences=int(occurrences))
        except PermissionError as e:
            return EditResult(error=str(e))
        except Exception as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        self._connect()
        try:
            base_physical = self._resolve_path(path)
        except ValueError:
            return []

        # --- Strategy 1: Remote find (fast) ---
        results = self._remote_glob(pattern, base_physical, path)
        if results is not None:
            return results

        # --- Strategy 2: Pure SFTP walk (fallback) ---
        effective_pattern = pattern.lstrip("/")
        results: list[FileInfo] = []

        for filepath, attr, _ in self._sftp_walk(base_physical):
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
            if is_dir:
                continue

            rel_path = filepath[len(base_physical):].lstrip("/")
            if not rel_path:
                continue

            if wcglob.globmatch(rel_path, effective_pattern, flags=wcglob.BRACE | wcglob.GLOBSTAR):
                vpath = self._to_virtual_path(filepath)
                results.append({
                    "path": vpath,
                    "is_dir": False,
                    "size": attr.st_size or 0,
                    "modified_at": datetime.fromtimestamp(attr.st_mtime or 0, timezone.utc).isoformat()
                })

        results.sort(key=lambda x: x.get("path", ""))
        return results

    def _remote_glob(self, pattern: str, base_physical: str, virtual_prefix: str) -> list[FileInfo] | None:
        """Try to use remote find command for fast glob matching.

        Returns None if the remote command is not available or fails.
        """
        if not self._check_remote_command("find", "_remote_find_available"):
            return None

        try:
            # Convert glob pattern to find-friendly expression.
            # For simple patterns like "*.py", use -name directly.
            # For complex patterns with slashes, use -path with glob.
            safe_pattern = shlex.quote(pattern.lstrip("/"))

            # Build find command: find <dir> -type f -name/-path <pattern>
            # Use -iname for case-insensitive match (matching wcmatch default behavior)
            if "/" not in pattern:
                find_cmd = f"find {shlex.quote(base_physical)} -type f -iname {safe_pattern} -maxdepth 100 2>/dev/null"
            else:
                find_cmd = f"find {shlex.quote(base_physical)} -type f -ipath {shlex.quote('*/' + pattern.lstrip('/'))} -maxdepth 100 2>/dev/null"

            code, stdout, stderr = self._exec_remote(find_cmd, timeout=20)
            if code != 0 and code != 1:  # 1 = no matches found (normal for find)
                return None

            if not stdout.strip():
                return []

            results: list[FileInfo] = []
            for line in stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                vpath = self._to_virtual_path(line)
                try:
                    # stat to get file size and mtime
                    assert self._sftp_client is not None
                    attr = self._sftp_client.stat(line)
                    results.append({
                        "path": vpath,
                        "is_dir": False,
                        "size": attr.st_size or 0,
                        "modified_at": datetime.fromtimestamp(attr.st_mtime or 0, timezone.utc).isoformat()
                    })
                except IOError:
                    # File might have been deleted between find and stat
                    results.append({
                        "path": vpath,
                        "is_dir": False,
                        "size": 0,
                        "modified_at": ""
                    })

            results.sort(key=lambda x: x.get("path", ""))
            return results
        except Exception as e:
            logger.debug("Remote glob failed, falling back to SFTP: %s", e)
            return None

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        self._connect()
        search_vpath = path or "/"
        try:
            base_physical = self._resolve_path(search_vpath)
        except ValueError:
            return []

        # --- Strategy 1: Remote ripgrep (fastest) ---
        matches = self._remote_ripgrep(pattern, base_physical, glob)
        if matches is not None:
            return matches

        # --- Strategy 2: Remote grep (fast) ---
        matches = self._remote_grep(pattern, base_physical, glob)
        if matches is not None:
            return matches

        # --- Strategy 3: Pure SFTP scan (fallback) ---
        return self._sftp_grep(pattern, base_physical, glob)

    def _remote_ripgrep(self, pattern: str, base_physical: str, glob: str | None) -> list[GrepMatch] | None:
        """Try to use remote ripgrep for fast search.

        Returns None if ripgrep is not available on the remote server.
        """
        if not self._check_remote_command("rg", "_remote_rg_available"):
            return None

        try:
            cmd_parts = ["rg", "--json", "-F"]  # -F for literal (fixed-string) search
            if glob:
                cmd_parts.extend(["--glob", shlex.quote(glob)])
            # Respect ignore_dirs
            for ignore_dir in self.ignore_dirs:
                cmd_parts.extend(["--glob", f"!{ignore_dir}"])
            cmd_parts.extend(["--max-filesize", str(self.max_file_size_bytes)])
            cmd_parts.extend(["--", shlex.quote(pattern), shlex.quote(base_physical)])
            cmd = " ".join(cmd_parts)

            code, stdout, _ = self._exec_remote(cmd, timeout=30)
            if code == 2:  # ripgrep returns 2 for errors
                return None
            # code 0 or 1 (1 = no matches) are both fine

            if not stdout.strip():
                return []

            matches: list[GrepMatch] = []
            for line in stdout.strip().splitlines():
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "match":
                    continue
                pdata = data.get("data", {})
                ftext = pdata.get("path", {}).get("text")
                if not ftext:
                    continue
                ln = pdata.get("line_number")
                lt = pdata.get("lines", {}).get("text", "").rstrip("\n")
                if ln is None:
                    continue
                vpath = self._to_virtual_path(ftext)
                matches.append({
                    "path": vpath,
                    "line": int(ln),
                    "text": lt
                })

            return matches
        except Exception as e:
            logger.debug("Remote ripgrep failed, falling back: %s", e)
            return None

    def _remote_grep(self, pattern: str, base_physical: str, glob: str | None) -> list[GrepMatch] | None:
        """Try to use remote standard grep for fast search.

        Returns None if grep is not available on the remote server.
        """
        if not self._check_remote_command("grep", "_remote_grep_available"):
            return None

        try:
            # Build grep command
            # -H: always print filename prefix (even for single file)
            cmd_parts = ["grep", "-rnFH", "--binary-files=without-match"]
            if glob:
                cmd_parts.extend(["--include", shlex.quote(glob)])
            # Exclude ignore_dirs
            for ignore_dir in self.ignore_dirs:
                cmd_parts.extend(["--exclude-dir", shlex.quote(ignore_dir)])
            cmd_parts.extend(["--", shlex.quote(pattern), shlex.quote(base_physical)])
            cmd = " ".join(cmd_parts)

            code, stdout, stderr = self._exec_remote(cmd, timeout=30)
            if code == 2:  # grep returns 2 for errors
                return None
            # code 0 (matches found) or 1 (no matches) are both fine

            if not stdout.strip():
                return []

            matches: list[GrepMatch] = []
            base_prefix = base_physical.rstrip("/") + "/"
            for line in stdout.strip().splitlines():
                # grep output format with -H:
                #   filepath:linenum:line_content
                parts = line.split(":", 2)
                if len(parts) != 3:
                    continue
                filepath, line_num_str, text = parts
                if not line_num_str.isdigit():
                    continue
                # Convert physical path to virtual path
                if filepath.startswith(base_prefix):
                    rel = filepath[len(base_prefix):]
                    vpath = "/" + rel
                else:
                    vpath = self._to_virtual_path(filepath)

                try:
                    matches.append({
                        "path": vpath,
                        "line": int(line_num_str),
                        "text": text
                    })
                except ValueError:
                    continue

            return matches
        except Exception as e:
            logger.debug("Remote grep failed, falling back: %s", e)
            return None

    def _sftp_grep(self, pattern: str, base_physical: str, glob: str | None) -> list[GrepMatch]:
        """Pure SFTP grep: download each file and scan locally (slow fallback)."""
        matches: list[GrepMatch] = []
        assert self._sftp_client is not None

        # If base_physical is a file (not a directory), search it directly
        try:
            base_attr = self._sftp_client.stat(base_physical)
            if not (stat.S_ISDIR(base_attr.st_mode) if base_attr.st_mode else False):
                if glob:
                    filename = posixpath.basename(base_physical)
                    if not wcglob.globmatch(filename, glob, flags=wcglob.BRACE):
                        return matches
                if base_attr.st_size and base_attr.st_size > self.max_file_size_bytes:
                    return matches
                try:
                    with self._sftp_client.open(base_physical, 'r') as f:
                        content = f.read().decode('utf-8')
                        for line_num, line in enumerate(content.splitlines(), 1):
                            if pattern in line:
                                vpath = self._to_virtual_path(base_physical)
                                matches.append({
                                    "path": vpath,
                                    "line": line_num,
                                    "text": line
                                })
                except (IOError, UnicodeDecodeError):
                    pass
                return matches
        except IOError:
            return []

        for filepath, attr, _ in self._sftp_walk(base_physical):
            if stat.S_ISDIR(attr.st_mode) if attr.st_mode else False:
                continue

            if glob:
                filename = posixpath.basename(filepath)
                if not wcglob.globmatch(filename, glob, flags=wcglob.BRACE):
                    continue

            if attr.st_size and attr.st_size > self.max_file_size_bytes:
                continue

            try:
                with self._sftp_client.open(filepath, 'r') as f:
                    content = f.read().decode('utf-8')
                    for line_num, line in enumerate(content.splitlines(), 1):
                        if pattern in line:
                            vpath = self._to_virtual_path(filepath)
                            matches.append({
                                "path": vpath,
                                "line": line_num,
                                "text": line
                            })
            except (IOError, UnicodeDecodeError):
                continue

        return matches

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        self._connect()
        responses: list[FileUploadResponse] = []
        for vpath, content in files:
            try:
                self._check_edit_permission(vpath)
                physical_path = self._resolve_path(vpath)
                parent_dir = posixpath.dirname(physical_path)
                self._sftp_mkdir_p(parent_dir)

                assert self._sftp_client is not None
                with self._sftp_client.open(physical_path, 'wb') as f:
                    f.write(content)
                responses.append(FileUploadResponse(path=vpath, error=None))
            except PermissionError:
                responses.append(FileUploadResponse(path=vpath, error="permission_denied"))
            except IOError:
                responses.append(FileUploadResponse(path=vpath, error="invalid_path"))
            except Exception:
                responses.append(FileUploadResponse(path=vpath, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self._connect()
        responses: list[FileDownloadResponse] = []
        for vpath in paths:
            try:
                physical_path = self._resolve_path(vpath)
                assert self._sftp_client is not None
                with self._sftp_client.open(physical_path, 'rb') as f:
                    content = f.read()
                responses.append(FileDownloadResponse(path=vpath, content=content, error=None))
            except IOError as e:
                if "No such file" in str(e):
                    responses.append(FileDownloadResponse(path=vpath, content=None, error="file_not_found"))
                elif "Permission denied" in str(e):
                    responses.append(FileDownloadResponse(path=vpath, content=None, error="permission_denied"))
                else:
                    responses.append(FileDownloadResponse(path=vpath, content=None, error="invalid_path"))
            except Exception:
                responses.append(FileDownloadResponse(path=vpath, content=None, error="invalid_path"))
        return responses
