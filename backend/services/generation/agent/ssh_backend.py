"""Pure SFTP Backend for DeepAgents.

Provides remote filesystem access via pure SFTP protocol.
Zero shell execution (no python3, grep, or mkdir commands are executed on the remote).
Highly stable, cross-platform (works on Linux, macOS, Windows OpenSSH), and secure.
"""

import fnmatch
import logging
import posixpath
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paramiko
import wcmatch.glob as wcglob

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

logger = logging.getLogger(__name__)


class PureSFTPBackend(BackendProtocol):
    """Backend that reads and writes files on a remote server using ONLY SFTP.

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

        # Default ignore list to prevent SFTP walk from hanging on massive directories
        if ignore_dirs is None:
            self.ignore_dirs = ['.git', 'node_modules', '__pycache__', '.venv', 'target', 'build', 'dist']
        else:
            self.ignore_dirs = ignore_dirs

        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        self._ssh_client: paramiko.SSHClient | None = None
        self._sftp_client: paramiko.SFTPClient | None = None

    def _connect(self) -> None:
        """Establish SSH and SFTP connections if not already connected."""
        if self._ssh_client is None or self._ssh_client.get_transport() is None or not self._ssh_client.get_transport().is_active():
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

    def close(self) -> None:
        """Close connections."""
        if self._sftp_client:
            self._sftp_client.close()
            self._sftp_client = None
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

    def __del__(self) -> None:
        self.close()

    # --- Path & Security Utils ---
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

    # --- Pure SFTP Helpers ---
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
                pass  # May have been created by a concurrent process

    def _sftp_walk(self, remotedir: str):
        """Pure SFTP recursive directory walker.

        Yields: (physical_path, SFTPAttributes)
        """
        assert self._sftp_client is not None
        try:
            attrs = self._sftp_client.listdir_attr(remotedir)
        except IOError:
            return

        for attr in attrs:
            filepath = posixpath.join(remotedir, attr.filename)
            is_dir = stat.S_ISDIR(attr.st_mode) if attr.st_mode else False

            yield filepath, attr

            # Skip heavy/unnecessary directories to speed up network traversal
            if is_dir and attr.filename not in self.ignore_dirs:
                yield from self._sftp_walk(filepath)

    # --- Protocol Implementation ---
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

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        self._connect()
        physical_path = self._resolve_path(file_path)
        try:
            assert self._sftp_client is not None
            with self._sftp_client.open(physical_path, 'r') as f:
                content = f.read().decode('utf-8')

            empty_msg = check_empty_content(content)
            if empty_msg:
                return empty_msg

            lines = content.splitlines()
            start_idx = offset
            end_idx = min(start_idx + limit, len(lines))

            if start_idx >= len(lines):
                return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

            selected_lines = lines[start_idx:end_idx]
            return format_content_with_line_numbers(selected_lines, start_line=start_idx + 1)
        except IOError as e:
            return f"Error reading file '{file_path}': {e}"
        except UnicodeDecodeError:
            return f"Error: File '{file_path}' is not a valid UTF-8 text file."

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

        effective_pattern = pattern.lstrip("/")
        results: list[FileInfo] = []

        # Local matching using wcmatch against remote SFTP tree
        for filepath, attr in self._sftp_walk(base_physical):
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

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        self._connect()
        search_vpath = path or "/"
        try:
            base_physical = self._resolve_path(search_vpath)
        except ValueError:
            return []

        matches: list[GrepMatch] = []
        assert self._sftp_client is not None

        for filepath, attr in self._sftp_walk(base_physical):
            if stat.S_ISDIR(attr.st_mode) if attr.st_mode else False:
                continue

            # 1. Glob filter
            if glob:
                filename = posixpath.basename(filepath)
                if not wcglob.globmatch(filename, glob, flags=wcglob.BRACE):
                    continue

            # 2. Size filter (prevent downloading massive files like DBs or binaries)
            if attr.st_size and attr.st_size > self.max_file_size_bytes:
                continue

            # 3. Read & Search locally
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
                continue  # Skip unreadable or non-text files

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
