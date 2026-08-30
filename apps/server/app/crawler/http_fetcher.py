import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.crawler.errors import (
    FetchConnectionError,
    FetchHttpError,
    FetchTimeoutError,
    UnsafeUrlError,
)


AddressResolver = Callable[[str, int], list[str]]
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class FetchResult:
    """普通 HTTP 抓取结果。"""

    html: str
    final_url: str


def resolve_host_addresses(hostname: str, port: int) -> list[str]:
    """解析主机的全部 TCP 地址。"""

    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchConnectionError("目标域名无法解析") from exc
    return list({record[4][0] for record in records})


class UrlSafetyValidator:
    """拒绝指向本机、内网和非全局地址的 URL。"""

    def __init__(self, resolver: AddressResolver = resolve_host_addresses) -> None:
        self._resolver = resolver

    def validate(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeUrlError("仅允许访问有效的 HTTP 或 HTTPS 公网地址")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeUrlError("不允许 URL 包含用户凭据")

        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise UnsafeUrlError("禁止访问本机或内部网络地址")

        try:
            addresses = [str(ipaddress.ip_address(hostname))]
        except ValueError:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = self._resolver(hostname, port)

        if not addresses:
            raise FetchConnectionError("目标域名无法解析")
        if any(not ipaddress.ip_address(address.split("%", 1)[0]).is_global for address in addresses):
            raise UnsafeUrlError("禁止访问本机或内部网络地址")


class HttpFetcher:
    """带超时、重定向控制和 SSRF 防护的普通 HTTP Fetcher。"""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_redirects: int,
        user_agent: str,
        validator: UrlSafetyValidator | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_redirects = max_redirects
        self._user_agent = user_agent
        self._validator = validator or UrlSafetyValidator()
        self._transport = transport

    def fetch(self, url: str) -> FetchResult:
        current_url = url
        with httpx.Client(
            timeout=httpx.Timeout(self._timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": self._user_agent, "Accept": "text/html,application/xhtml+xml"},
            transport=self._transport,
        ) as client:
            for redirect_count in range(self._max_redirects + 1):
                self._validator.validate(current_url)
                response = self._request(client, current_url)

                if response.status_code in REDIRECT_STATUSES:
                    if redirect_count >= self._max_redirects:
                        raise FetchHttpError("网页重定向次数过多")
                    location = response.headers.get("location")
                    if not location:
                        raise FetchHttpError("网页返回了无目标地址的重定向")
                    current_url = urljoin(current_url, location)
                    self._validator.validate(current_url)
                    continue

                self._ensure_success(response)
                return FetchResult(html=response.text, final_url=str(response.url))

        raise FetchHttpError("网页重定向次数过多")

    @staticmethod
    def _request(client: httpx.Client, url: str) -> httpx.Response:
        try:
            return client.get(url)
        except httpx.TimeoutException as exc:
            raise FetchTimeoutError("网页请求超时") from exc
        except httpx.ConnectError as exc:
            raise FetchConnectionError("无法连接目标网页") from exc
        except httpx.RequestError as exc:
            raise FetchConnectionError("网页请求失败") from exc

    @staticmethod
    def _ensure_success(response: httpx.Response) -> None:
        if response.status_code == 403:
            raise FetchHttpError("目标网页拒绝访问（HTTP 403）")
        if response.status_code == 404:
            raise FetchHttpError("目标网页不存在（HTTP 404）")
        if response.status_code >= 400:
            raise FetchHttpError(f"目标网页返回 HTTP {response.status_code}")
        if response.status_code >= 300:
            raise FetchHttpError(f"目标网页返回不支持的 HTTP {response.status_code}")

        content_type = response.headers.get("content-type", "").lower()
        if content_type and "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise FetchHttpError("目标地址返回的不是 HTML 网页")
