"""HTTP API 客户端：薄封装 httpx，只关心 mambo 后端 REST API。"""
from __future__ import annotations

import httpx


class ApiError(Exception):
    """API 调用失败（HTTP 错误码或连接失败）。"""

    def __init__(self, status_code: int, detail, method: str, url: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.url = url

    def __str__(self) -> str:
        if self.status_code == 0:
            return f"无法连接后端: {self.detail}"
        if isinstance(self.detail, str):
            return f"API 错误 {self.status_code}: {self.detail}"
        if isinstance(self.detail, list):
            parts = []
            for item in self.detail:
                if isinstance(item, dict):
                    loc = ".".join(str(x) for x in item.get("loc", []))
                    parts.append(f"{loc}: {item.get('msg', '')}")
            return f"API 错误 {self.status_code}: " + "; ".join(parts)
        return f"API 错误 {self.status_code}: {self.detail}"


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, headers={"Accept": "application/json"})

    def close(self) -> None:
        self._http.close()

    # ---- 底层请求 ----
    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(0, f"{type(exc).__name__}: {exc}", method, url)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ApiError(resp.status_code, detail, method, url)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ---- Providers ----
    def list_providers(self):
        return self._request("GET", "/api/providers/")

    def create_provider(self, data: dict):
        return self._request("POST", "/api/providers/", json=data)

    def update_provider(self, provider_id: str, data: dict):
        return self._request("PUT", f"/api/providers/{provider_id}", json=data)

    def delete_provider(self, provider_id: str):
        return self._request("DELETE", f"/api/providers/{provider_id}")

    def test_provider(self, provider_id: str, api_host: str, use_proxy: bool = False):
        return self._request(
            "POST",
            f"/api/providers/{provider_id}/test-connection",
            params={"use_proxy": "true" if use_proxy else "false"},
            json={"apiHost": api_host},
        )

    def fetch_provider_models(self, provider_id: str, use_proxy: bool = False):
        return self._request(
            "GET",
            f"/api/providers/{provider_id}/fetch-models",
            params={"use_proxy": "true" if use_proxy else "false"},
        )

    # ---- Models ----
    def create_model(self, data: dict):
        return self._request("POST", "/api/models/", json=data)

    def update_model(self, model_id: str, data: dict):
        return self._request("PUT", f"/api/models/{model_id}", json=data)

    def delete_model(self, model_id: str):
        return self._request("DELETE", f"/api/models/{model_id}")

    # ---- Global Settings ----
    def get_global_settings(self):
        return self._request("GET", "/api/settings/global")

    def update_global_settings(self, data: dict):
        return self._request("PUT", "/api/settings/global", json=data)

    # ---- Resources ----
    def list_resources(self):
        return self._request("GET", "/api/resources")

    def get_resource(self, resource_id: str):
        return self._request("GET", f"/api/resources/{resource_id}")

    def create_resource(self, data: dict):
        return self._request("POST", "/api/resources", json=data)

    def update_resource(self, resource_id: str, data: dict):
        return self._request("PUT", f"/api/resources/{resource_id}", json=data)

    def delete_resource(self, resource_id: str):
        return self._request("DELETE", f"/api/resources/{resource_id}")

    def move_resources(self, item_ids: list[str], reference_id: str, action: str = "inside"):
        return self._request("POST", "/api/resources/move", json={
            "item_ids": item_ids,
            "reference_id": reference_id,
            "action": action,
        })

    def upload_resource_file(self, file_bytes: bytes, filename: str, mime: str,
                             parent_id: str | None = None, resource_id: str | None = None):
        data = {}
        if parent_id:
            data["parent_id"] = parent_id
        if resource_id:
            data["resource_id"] = resource_id
        return self._request(
            "POST", "/api/resources/upload",
            files={"file": (filename, file_bytes, mime)},
            data=data,
        )

    def search_resources(self, keyword: str, root_id: str | None = None,
                         enable_regex: bool = False, page_num: int = 1, page_size: int = 20):
        return self._request("POST", "/api/resources/search", json={
            "keyword": keyword,
            "root_id": root_id,
            "enable_regex": enable_regex,
            "page_num": page_num,
            "page_size": page_size,
        })

    # ---- Resource Versions ----
    def create_resource_version(self, resource_id: str, data: dict):
        return self._request("POST", f"/api/resources/{resource_id}/versions", json=data)

    def set_active_version(self, resource_id: str, version_id: str):
        return self._request("PUT", f"/api/resources/{resource_id}/set-active/{version_id}")

    def delete_resource_version(self, version_id: str):
        return self._request("DELETE", f"/api/resources/versions/{version_id}")

    # ---- Files ----
    def upload_file(self, file_bytes: bytes, filename: str, mime: str):
        return self._request("POST", "/api/files/upload",
                             files={"file": (filename, file_bytes, mime)})

    def get_file_content(self, file_id: str):
        return self._request("GET", f"/api/files/{file_id}/content")

    # ---- Skills ----
    def create_skill(self, data: dict):
        return self._request("POST", "/api/resources/skills", json=data)

    def validate_skill(self, resource_id: str):
        return self._request("GET", f"/api/resources/skills/{resource_id}/validate")

    def import_skill_file(self, file_bytes: bytes, filename: str,
                          parent_id: str | None = None, on_conflict: str = "error"):
        data = {"on_conflict": on_conflict}
        if parent_id:
            data["parent_id"] = parent_id
        return self._request(
            "POST", "/api/resources/skills/import/file",
            files={"file": (filename, file_bytes, "application/octet-stream")},
            data=data,
        )

    def import_skill_github(self, repo_url: str, parent_id: str | None = None,
                            on_conflict: str = "error"):
        data = {"repo_url": repo_url, "on_conflict": on_conflict}
        if parent_id:
            data["parent_id"] = parent_id
        return self._request("POST", "/api/resources/skills/import/github", json=data)


def with_api(func):
    """装饰领域命令函数：自动创建 / 关闭 ApiClient。"""

    def wrapper(args):
        api = ApiClient(args.base_url, args.timeout)
        try:
            return func(args, api)
        finally:
            api.close()

    return wrapper
