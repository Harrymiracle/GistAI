from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.agent.schemas import WebSearchInput, WebSearchResult
from app.agent.web_search import (
    TavilyWebSearchProvider,
    WebSearchService,
    WebSearchConfigurationError,
    WebSearchHttpError,
    WebSearchResponseError,
    WebSearchTimeoutError,
)
from app.core.config import Settings


class RecordingWebSearchProvider:
    def __init__(self, results: list[WebSearchResult]) -> None:
        self.results = results
        self.inputs: list[WebSearchInput] = []

    def search(self, payload: WebSearchInput) -> list[WebSearchResult]:
        self.inputs.append(payload)
        return self.results


def test_web_search_input_enforces_query_and_result_limit() -> None:
    payload = WebSearchInput(query="  LangGraph 最新版本  ", max_results=10)

    assert payload.query == "LangGraph 最新版本"
    assert payload.max_results == 10
    for invalid_limit in (0, 11):
        with pytest.raises(ValidationError):
            WebSearchInput(query="LangGraph", max_results=invalid_limit)


def test_web_search_settings_have_safe_defaults_and_limits() -> None:
    settings = Settings(
        _env_file=None,
        web_search_base_url="https://api.tavily.test",
        web_search_api_key="unit-test-key",
        web_search_timeout_seconds=5,
        web_search_max_results=5,
    )

    assert settings.web_search_base_url == "https://api.tavily.test"
    assert settings.web_search_api_key.get_secret_value() == "unit-test-key"
    assert settings.web_search_timeout_seconds == 5
    assert settings.web_search_max_results == 5
    with pytest.raises(ValidationError):
        Settings(_env_file=None, web_search_max_results=11)


def test_web_search_service_keeps_provider_replaceable() -> None:
    result = WebSearchResult(
        title="Result",
        url="https://example.com/result",
        snippet="Snippet",
        source="example.com",
    )
    provider = RecordingWebSearchProvider([result])
    service = WebSearchService(provider, max_results=4)

    assert service.search("query") == [result]
    assert provider.inputs == [WebSearchInput(query="query", max_results=4)]


def test_tavily_provider_maps_search_snippets_without_requesting_full_content() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "LangGraph Release",
                        "url": "https://docs.example.com/langgraph",
                        "content": "Version 2.0 was released today.",
                        "score": 0.91,
                        "published_date": "2026-09-14",
                        "raw_content": "不允许进入 Agent 的网页全文",
                    }
                ]
            },
        )

    provider = TavilyWebSearchProvider(
        base_url="https://api.tavily.test",
        api_key=SecretStr("unit-test-key"),
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    results = provider.search(WebSearchInput(query="LangGraph", max_results=3))

    assert results == [
        WebSearchResult(
            title="LangGraph Release",
            url="https://docs.example.com/langgraph",
            snippet="Version 2.0 was released today.",
            source="docs.example.com",
            published_at="2026-09-14",
        )
    ]
    assert captured["url"] == "https://api.tavily.test/search"
    assert captured["authorization"] == "Bearer unit-test-key"
    assert '"search_depth":"basic"' in captured["body"]
    assert '"include_answer":false' in captured["body"]
    assert '"include_raw_content":false' in captured["body"]
    assert '"include_images":false' in captured["body"]
    assert '"max_results":3' in captured["body"]


def test_tavily_provider_treats_empty_results_as_success() -> None:
    provider = TavilyWebSearchProvider(
        base_url="https://api.tavily.test",
        api_key=SecretStr("unit-test-key"),
        timeout_seconds=3,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": []})
        ),
    )

    assert provider.search(WebSearchInput(query="unknown")) == []


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (httpx.Response(302), WebSearchHttpError),
        (httpx.Response(432), WebSearchHttpError),
        (httpx.Response(200, json={"unexpected": []}), WebSearchResponseError),
        (
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Broken",
                            "url": "not-a-url",
                            "content": "snippet",
                        }
                    ]
                },
            ),
            WebSearchResponseError,
        ),
    ],
)
def test_tavily_provider_maps_http_and_invalid_response_errors(
    response: httpx.Response,
    expected_error: type[Exception],
) -> None:
    provider = TavilyWebSearchProvider(
        base_url="https://api.tavily.test",
        api_key=SecretStr("unit-test-key"),
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: response),
    )

    with pytest.raises(expected_error):
        provider.search(WebSearchInput(query="LangGraph"))


def test_tavily_provider_maps_timeout_without_leaking_request_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive timeout detail", request=request)

    provider = TavilyWebSearchProvider(
        base_url="https://api.tavily.test",
        api_key=SecretStr("unit-test-key"),
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WebSearchTimeoutError, match="Web Search 请求超时") as exc_info:
        provider.search(WebSearchInput(query="LangGraph"))

    assert "sensitive timeout detail" not in str(exc_info.value)


def test_tavily_provider_rejects_missing_configuration_before_http_call() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"results": []})

    provider = TavilyWebSearchProvider(
        base_url="https://api.tavily.test",
        api_key=SecretStr(""),
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(WebSearchConfigurationError):
        provider.search(WebSearchInput(query="LangGraph"))

    assert called is False
