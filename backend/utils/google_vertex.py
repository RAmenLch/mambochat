# backend/utils/google_vertex.py
"""Agent Platform（原 Vertex AI）接入辅助。

Gemini 有两套 API 面：

- Gemini Developer API：``generativelanguage.googleapis.com/v1beta``，API key 鉴权；
- Gemini Enterprise Agent Platform（原 Vertex AI）：``{location}-aiplatform.googleapis.com``，
  资源路径为 ``/v1/projects/{project}/locations/{location}/publishers/google/models/{model}``，
  常规用 OAuth，也接受绑定服务账号的 API key（``x-goog-api-key``）。

本项目不新增执行器，仍复用 ``google`` worker：服务商的 ``apiHost`` 直接写平台的资源前缀

    https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}

即可被识别为平台侧配置。``google-genai`` 的 ``Client`` 不允许 ``api_key`` 与
``project/location`` 同时传入（两者显式互斥），但 ``HttpOptions`` 支持
``base_url`` + ``ResourceScope.COLLECTION``：此时 SDK 只往 base_url 后面拼
``publishers/google/models/{model}:generateContent``，不再补 projects/locations。
本模块据此把项目路径固化进 base_url，从而用 API key 调平台侧模型。
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

_VERTEX_HOST_SUFFIX = "aiplatform.googleapis.com"
_PATH_RE = re.compile(r"/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)")
_HOST_REGION_RE = re.compile(r"^(?P<location>[a-z0-9-]+)-aiplatform\.googleapis\.com$")
_HOST_MULTI_REGION_RE = re.compile(r"^aiplatform\.(?P<location>[a-z0-9-]+)\.rep\.googleapis\.com$")


@dataclass(frozen=True)
class VertexEndpoint:
    """Agent Platform 的资源定位：项目、区域与实际请求主机。"""

    project: str
    location: str
    host: str = _VERTEX_HOST_SUFFIX

    @property
    def base_url(self) -> str:
        """配合 ``ResourceScope.COLLECTION`` 使用的基础地址。

        SDK 会在这个地址后拼 ``publishers/google/models/{model}:generateContent``，
        因此这里不能带 ``/publishers/google``，也不要带版本号之外的其它前缀。
        """
        return (
            f"https://{self.host}/v1beta1"
            f"/projects/{self.project}/locations/{self.location}"
        )


def is_vertex_api_host(api_host: Optional[str]) -> bool:
    """判断 apiHost 是否指向 Agent Platform（不校验路径是否完整）。"""
    if not api_host:
        return False
    host = (urlparse(api_host.strip()).hostname or "").lower()
    return host.endswith(_VERTEX_HOST_SUFFIX)


def _location_from_host(host: str) -> str:
    multi = _HOST_MULTI_REGION_RE.match(host)
    if multi:
        return multi.group("location")
    single = _HOST_REGION_RE.match(host)
    if single:
        return single.group("location")
    return "global"


def _host_supports_location(host: str, location: str) -> bool:
    """host 与 location 必须匹配，否则 Google 会返回 400 Invalid hostname。

    全局主机 ``aiplatform.googleapis.com`` 可以配合任意 location 使用。
    """
    if host == _VERTEX_HOST_SUFFIX:
        return True
    if host == f"aiplatform.{location}.rep.googleapis.com":
        return True
    return host == f"{location}-aiplatform.googleapis.com"


def parse_vertex_api_host(api_host: str) -> Optional[VertexEndpoint]:
    """把服务商的 apiHost 解析成 Agent Platform 资源定位。

    非 Agent Platform 的地址返回 ``None``；是 Agent Platform 但路径缺项目/区域时
    抛出 ``ValueError``，避免后续请求打到错误地址。
    """
    if not is_vertex_api_host(api_host):
        return None

    parsed = urlparse(api_host.strip())
    host = (parsed.hostname or "").lower()
    match = _PATH_RE.search(parsed.path or "")
    if not match:
        raise ValueError(
            "Agent Platform 的 API Host 必须包含项目与区域，例如 "
            "https://aiplatform.googleapis.com/v1/projects/你的项目ID/locations/global"
        )

    project = match.group("project")
    location = match.group("location")
    if not _host_supports_location(host, location):
        raise ValueError(
            f"API Host 与区域不一致：host={host}, location={location}。"
            f"请使用 https://aiplatform.googleapis.com 或 "
            f"https://{location}-aiplatform.googleapis.com"
        )
    return VertexEndpoint(project=project, location=location, host=host)


def build_vertex_client(
        endpoint: VertexEndpoint,
        api_key: str,
        proxy_url: Optional[str] = None,
):
    """构造指向指定项目/区域的 ``google-genai`` Client（API key 鉴权）。"""
    from google import genai
    from google.genai.types import HttpOptions, ResourceScope

    client_args = {"proxy": proxy_url} if proxy_url else None
    http_options = HttpOptions(
        base_url=endpoint.base_url,
        base_url_resource_scope=ResourceScope.COLLECTION,
        client_args=client_args,
        async_client_args=client_args,
    )
    return genai.Client(vertexai=True, api_key=api_key, http_options=http_options)
