# backend/services/generation/agent/tree_extension.py

from abc import abstractmethod
import asyncio
from typing import Any, Dict, Annotated

from langchain_core.tools import StructuredTool
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime

from deepagents.backends.protocol import BackendProtocol
from deepagents.backends.state import StateBackend
from deepagents.backends.composite import CompositeBackend, _route_for_path


# ==========================================
# 1. Protocol Definition
# ==========================================
class TreeBackendProtocol(BackendProtocol):
    """Protocol extension for backends supporting compact tree generation."""

    @abstractmethod
    def tree(self, path: str = "/", depth: int = 3) -> str:
        """Generate a compact directory tree string optimized for LLM context."""
        pass

    async def atree(self, path: str = "/", depth: int = 3) -> str:
        """Async wrapper that dispatches the synchronous tree method to a thread."""
        return await asyncio.to_thread(self.tree, path, depth)


# ==========================================
# 1.5 Execution Control Proxy
# ==========================================
class _NonExecutableBackendProxy(TreeBackendProtocol):
    """Wraps a backend so that isinstance(proxy, SandboxBackendProtocol) is False.

    This causes deepagents' FilesystemMiddleware to automatically hide the
    execute tool from the LLM (see ``_supports_execution()`` in the library).

    Inherits TreeBackendProtocol so that isinstance(proxy, TreeBackendProtocol)
    still returns True when the wrapped backend supports tree.
    """

    def __init__(self, backend) -> None:
        object.__setattr__(self, "_inner", backend)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def tree(self, path: str = "/", depth: int = 3) -> str:
        return self._inner.tree(path, depth)

    async def atree(self, path: str = "/", depth: int = 3) -> str:
        return await self._inner.atree(path, depth)


# ==========================================
# 2. Backend Implementations
# ==========================================
class TreeStateBackend(StateBackend, TreeBackendProtocol):

    def tree(self, path: str = "/", depth: int = 3) -> str:
        files = self.runtime.state.get("files", {})
        tree_dict: Dict[str, Any] = {}
        norm_path = path if path.endswith("/") else path + "/"

        for k in files.keys():
            if not k.startswith(norm_path):
                continue
            rel_path = k[len(norm_path):].lstrip("/")
            if not rel_path:
                continue
            parts = rel_path.split("/")
            current = tree_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = None

        if not tree_dict:
            return f"No files found in {path}"

        lines = [path]

        def _format_tree(node: Dict[str, Any], current_depth: int) -> None:
            indent = "  " * current_depth
            sorted_items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))

            for k, v in sorted_items:
                if v is None:
                    lines.append(f"{indent}{k}")
                else:
                    if not v:
                        lines.append(f"{indent}{k}/ (empty)")
                    elif current_depth >= depth:
                        lines.append(f"{indent}{k}/ ... (unexpanded)")
                    else:
                        curr_k = k
                        curr_v = v
                        while isinstance(curr_v, dict) and len(curr_v) == 1:
                            only_key = list(curr_v.keys())[0]
                            if curr_v[only_key] is None:
                                break
                            curr_k = f"{curr_k}/{only_key}"
                            curr_v = curr_v[only_key]

                        lines.append(f"{indent}{curr_k}/")
                        if isinstance(curr_v, dict):
                            _format_tree(curr_v, current_depth + 1)

        _format_tree(tree_dict, 1)
        return "\n".join(lines)


class TreeCompositeBackend(CompositeBackend, TreeBackendProtocol):
    """CompositeBackend with tree support routing."""

    async def atree(self, path: str = "/", depth: int = 3) -> str:
        """Async tree method — directly awaits child backends' atree to avoid
        creating extra event loops (which breaks WebSocket communication on
        Windows when futures are resolved across loops)."""

        backend, backend_path, route_prefix = _route_for_path(
            default=self.default,
            sorted_routes=self.sorted_routes,
            path=path,
        )

        # ---------- matched a specific route ----------
        if route_prefix is not None:
            if isinstance(backend, TreeBackendProtocol):
                try:
                    raw_tree = await backend.atree(backend_path, depth)
                except Exception as e:
                    return f"Error: {e}"
            else:
                return f"Error: Backend mounted at {route_prefix} does not support tree."
            lines = raw_tree.splitlines()
            if lines:
                lines[0] = path
            return "\n".join(lines)

        # ---------- aggregate root "/" ----------
        if path == "/":
            lines = [path]

            # default backend
            if isinstance(self.default, TreeBackendProtocol):
                default_tree = await self.default.atree("/", depth)
                default_lines = default_tree.splitlines()
                if len(default_lines) > 1:
                    lines.extend(default_lines[1:])

            # route backends
            for r_prefix, b in self.sorted_routes:
                r_name = r_prefix.strip("/")
                if depth > 1:
                    if isinstance(b, TreeBackendProtocol):
                        try:
                            b_tree = await b.atree("/", depth - 1)
                        except Exception as e:
                            lines.append(f"  {r_name}/ [offline] {e}")
                            continue
                        if b_tree.startswith("Error"):
                            lines.append(f"  {r_name}/ [offline] {b_tree}")
                            continue
                        b_lines = b_tree.splitlines()
                        if len(b_lines) > 1:
                            lines.append(f"  {r_name}/")
                            lines.extend([f"  {line}" for line in b_lines[1:]])
                        else:
                            lines.append(f"  {r_name}/ (empty)")
                    else:
                        lines.append(f"  {r_name}/ ... (unexpanded)")
                else:
                    lines.append(f"  {r_name}/ ... (unexpanded)")
            return "\n".join(lines)

        # ---------- fall through to default ----------
        if isinstance(self.default, TreeBackendProtocol):
            return await self.default.atree(path, depth)

        return "Error: Default backend does not support tree."

    def tree(self, path: str = "/", depth: int = 3) -> str:
        backend, backend_path, route_prefix = _route_for_path(
            default=self.default,
            sorted_routes=self.sorted_routes,
            path=path,
        )

        if route_prefix is not None:
            if isinstance(backend, TreeBackendProtocol):
                raw_tree = backend.tree(backend_path, depth)
                lines = raw_tree.splitlines()
                if lines:
                    lines[0] = path
                return "\n".join(lines)
            return f"Error: Backend mounted at {route_prefix} does not support tree."

        if path == "/":
            lines = [path]
            if isinstance(self.default, TreeBackendProtocol):
                default_lines = self.default.tree("/", depth).splitlines()
                if len(default_lines) > 1:
                    lines.extend(default_lines[1:])

            for r_prefix, b in self.sorted_routes:
                r_name = r_prefix.strip("/")
                if depth > 1 and isinstance(b, TreeBackendProtocol):
                    b_lines = b.tree("/", depth - 1).splitlines()
                    if len(b_lines) > 1:
                        lines.append(f"  {r_name}/")
                        lines.extend([f"  {line}" for line in b_lines[1:]])
                    else:
                        lines.append(f"  {r_name}/ (empty)")
                else:
                    lines.append(f"  {r_name}/ ... (unexpanded)")
            return "\n".join(lines)

        if isinstance(self.default, TreeBackendProtocol):
            return self.default.tree(path, depth)

        return "Error: Default backend does not support tree."


# ==========================================
# 3. Context Injection & Middleware
# ==========================================
class TreeMiddleware(AgentMiddleware):
    """Middleware for providing the tree tool to an agent."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.tools = [self._create_tree_tool()]

    def _get_backend(self, runtime: ToolRuntime) -> Any:
        if callable(self.backend):
            return self.backend(runtime)
        return self.backend

    def _create_tree_tool(self) -> StructuredTool:
        def sync_tree(
            runtime: ToolRuntime,
            path: Annotated[str, "Directory path to inspect. Use '/' for root."] = "/",
            depth: Annotated[int, "Maximum depth to traverse. Keep it small to save tokens."] = 3,
        ) -> str:
            try:
                backend = self._get_backend(runtime)
                if isinstance(backend, TreeBackendProtocol):
                    return backend.tree(path, depth)
                return "Error: The current backend configuration does not support the tree operation."
            except Exception as e:
                return f"Error executing tree: {str(e)}"

        async def async_tree(
            runtime: ToolRuntime,
            path: Annotated[str, "Directory path to inspect. Use '/' for root."] = "/",
            depth: Annotated[int, "Maximum depth to traverse. Keep it small to save tokens."] = 3,
        ) -> str:
            try:
                backend = self._get_backend(runtime)
                if isinstance(backend, TreeBackendProtocol):
                    return await backend.atree(path, depth)
                return "Error: The current backend configuration does not support the tree operation."
            except Exception as e:
                return f"Error executing tree: {str(e)}"

        return StructuredTool.from_function(
            func=sync_tree,
            coroutine=async_tree,
            name="tree",
            description="Get a highly compact directory tree structure. Useful for quickly understanding project layout.",
        )
