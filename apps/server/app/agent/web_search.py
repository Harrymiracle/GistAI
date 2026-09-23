from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from app.agent.schemas import WebSearchInput, WebSearchResult


class WebSearchError(Exception):
    """外部搜索错误的安全基础类型。"""


class WebSearchConfigurationError(WebSearchError):
    """外部搜索必要配置缺失或无效。"""


class WebSearchTimeoutError(WebSearchError):
    """外部搜索请求超时。"""


class WebSearchConnectionError(WebSearchError):
    """无法连接外部搜索服务。"""


class WebSearchHttpError(WebSearchError):
    """外部搜索服务返回错误状态。"""


class WebSearchResponseError(WebSearchError):
    """外部搜索服务返回无效结构。"""


class WebSearchProvider(Protocol):
    """WebSearchService 依赖的厂商适配接口。"""

    def search(self, payload: WebSearchInput) -> list[WebSearchResult]: ...


class WebSearchServiceProvider(Protocol):
    """Agent Runtime 依赖的厂商无关搜索服务接口。"""

    def search(self, query: str) -> list[WebSearchResult]: ...


class WebSearchService:
    """向 Agent 暴露稳定接口，并隔离具体搜索厂商。"""

    def __init__(self, provider: WebSearchProvider, *, max_results: int) -> None:
        self._provider = provider
        self._max_results = max_results

    def search(self, query: str) -> list[WebSearchResult]:
        return self._provider.search(
            WebSearchInput(query=query, max_results=self._max_results)
        )


class TavilyWebSearchProvider:
    """通过 Tavily Search API 返回搜索摘要，不请求网页全文。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key.get_secret_value().strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def search(self, payload: WebSearchInput) -> list[WebSearchResult]:
        self._ensure_configured()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout_seconds),
                transport=self._transport,
            ) as client:
                response = client.post(
                    f"{self._base_url}/search",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "query": payload.query,
                        "max_results": payload.max_results,
                        "search_depth": "basic",
                        "include_answer": False,
                        "include_raw_content": False,
                        "include_images": False,
                    },
                )
        except httpx.TimeoutException as exc:
            raise WebSearchTimeoutError("Web Search 请求超时") from exc
        except httpx.RequestError as exc:
            raise WebSearchConnectionError("无法连接 Web Search 服务") from exc

        if response.status_code >= 300:
            raise WebSearchHttpError(
                f"Web Search Provider 返回 HTTP {response.status_code}"
            )
        try:
            body = response.json()
            raw_results = body["results"]
            if not isinstance(raw_results, list):
                raise TypeError("results 不是列表")
            return [self._map_result(item) for item in raw_results]
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise WebSearchResponseError("Web Search Provider 返回无效结构") from exc

    def _ensure_configured(self) -> None:
        missing = []
        if not self._base_url:
            missing.append("WEB_SEARCH_BASE_URL")
        if not self._api_key:
            missing.append("WEB_SEARCH_API_KEY")
        if missing:
            raise WebSearchConfigurationError(
                f"Web Search 配置缺失：{', '.join(missing)}"
            )
        if not self._api_key.isascii():
            raise WebSearchConfigurationError("WEB_SEARCH_API_KEY 必须使用 ASCII 字符")

    @staticmethod
    def _map_result(item: Any) -> WebSearchResult:
        if not isinstance(item, dict):
            raise TypeError("搜索结果不是对象")
        url = item["url"]
        source = urlsplit(str(url)).hostname
        if not source:
            raise ValueError("搜索结果 URL 无效")
        return WebSearchResult(
            title=item["title"],
            url=url,
            snippet=item["content"],
            source=source,
            published_at=item.get("published_date"),
        )
