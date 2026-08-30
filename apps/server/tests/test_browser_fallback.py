import hashlib
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_crawler_service
from app.crawler.browser_fetcher import PlaywrightFetcher
from app.crawler.errors import (
    CrawlerFallbackError,
    FetchConnectionError,
    FetchTimeoutError,
    UnsafeUrlError,
)
from app.crawler.extractor import ArticleExtractor
from app.crawler.http_fetcher import FetchResult, UrlSafetyValidator
from app.crawler.service import CrawlerService
from app.main import app
from app.models.article import Article


PUBLIC_URL = "https://public.example/dynamic"
PUBLIC_ADDRESS = "93.184.216.34"
VALID_BODY = "浏览器渲染后得到的文章正文，用于验证 Playwright fallback 和数据库持久化。" * 15
VALID_HTML = f"<html><head><title>动态文章</title></head><body><article>{VALID_BODY}</article></body></html>"
SHORT_HTML = "<html><body><article>内容太短</article></body></html>"


class StubFetcher:
    """记录调用次数的 HTML Fetcher 测试替身。"""

    def __init__(self, result: FetchResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, _url: str) -> FetchResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def crawler_with_stubs(http_fetcher: Any, browser_fetcher: Any) -> CrawlerService:
    return CrawlerService(
        fetcher=http_fetcher,
        browser_fetcher=browser_fetcher,
        extractor=ArticleExtractor(min_content_chars=100),
    )


def test_http_success_does_not_start_playwright() -> None:
    http_fetcher = StubFetcher(FetchResult(VALID_HTML, PUBLIC_URL))
    browser_fetcher = StubFetcher(error=AssertionError("不应启动 Playwright"))

    result = crawler_with_stubs(http_fetcher, browser_fetcher).fetch_article(PUBLIC_URL)

    assert VALID_BODY[:30] in result.clean_content
    assert http_fetcher.calls == 1
    assert browser_fetcher.calls == 0


def test_http_failure_falls_back_to_playwright() -> None:
    http_fetcher = StubFetcher(error=FetchConnectionError("普通 HTTP 连接失败"))
    browser_fetcher = StubFetcher(FetchResult(VALID_HTML, PUBLIC_URL))

    result = crawler_with_stubs(http_fetcher, browser_fetcher).fetch_article(PUBLIC_URL)

    assert VALID_BODY[:30] in result.clean_content
    assert http_fetcher.calls == 1
    assert browser_fetcher.calls == 1


def test_short_http_content_falls_back_to_playwright() -> None:
    http_fetcher = StubFetcher(FetchResult(SHORT_HTML, PUBLIC_URL))
    browser_fetcher = StubFetcher(FetchResult(VALID_HTML, PUBLIC_URL))

    result = crawler_with_stubs(http_fetcher, browser_fetcher).fetch_article(PUBLIC_URL)

    assert len(result.clean_content) >= 100
    assert browser_fetcher.calls == 1


def test_http_and_playwright_fail_with_stage_information() -> None:
    http_fetcher = StubFetcher(error=FetchConnectionError("普通 HTTP 连接失败"))
    browser_fetcher = StubFetcher(error=FetchTimeoutError("Playwright 加载网页超时"))

    with pytest.raises(CrawlerFallbackError) as exc_info:
        crawler_with_stubs(http_fetcher, browser_fetcher).fetch_article(PUBLIC_URL)

    message = str(exc_info.value)
    assert "普通 HTTP 阶段失败" in message
    assert "Playwright 阶段失败" in message
    assert "加载网页超时" in message


def test_playwright_fallback_persists_content_hash_and_final_status(
    client: TestClient,
    db_session: Session,
) -> None:
    http_fetcher = StubFetcher(error=FetchConnectionError("普通 HTTP 连接失败"))
    browser_fetcher = StubFetcher(FetchResult(VALID_HTML, PUBLIC_URL))
    app.dependency_overrides[get_crawler_service] = lambda: crawler_with_stubs(
        http_fetcher,
        browser_fetcher,
    )

    response = client.post(
        "/api/v1/articles",
        json={"source_url": PUBLIC_URL, "source_type": "web"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    expected_hash = hashlib.sha256(data["clean_content"].encode("utf-8")).hexdigest()
    assert data["fetch_status"] == "completed"
    assert data["fetch_error"] is None
    assert data["status"] == "processing"
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "pending"
    assert data["content_hash"] == expected_hash

    persisted = db_session.scalar(select(Article).where(Article.id == data["id"]))
    assert persisted is not None
    assert persisted.clean_content == data["clean_content"]
    assert persisted.content_hash == expected_hash


def test_both_stages_fail_but_article_is_retained(
    client: TestClient,
    db_session: Session,
) -> None:
    http_fetcher = StubFetcher(error=FetchConnectionError("普通 HTTP 连接失败"))
    browser_fetcher = StubFetcher(error=FetchTimeoutError("Playwright 加载网页超时"))
    app.dependency_overrides[get_crawler_service] = lambda: crawler_with_stubs(
        http_fetcher,
        browser_fetcher,
    )

    response = client.post(
        "/api/v1/articles",
        json={"source_url": PUBLIC_URL, "source_type": "web"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["fetch_status"] == "failed"
    assert "普通 HTTP 阶段失败" in data["fetch_error"]
    assert "Playwright 阶段失败" in data["fetch_error"]
    assert data["clean_content"] is None
    assert data["ai_status"] == "pending"
    assert data["embedding_status"] == "pending"
    assert db_session.scalar(select(Article.id).where(Article.id == data["id"])) == data["id"]


@dataclass
class FakeResponse:
    status: int = 200


class FakeRequest:
    def __init__(self, url: str, navigation: bool) -> None:
        self.url = url
        self._navigation = navigation

    def is_navigation_request(self) -> bool:
        return self._navigation


class FakeRoute:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.aborted = False
        self.continued = False

    def abort(self, _error_code: str | None = None) -> None:
        self.aborted = True

    def continue_(self) -> None:
        self.continued = True


class FakePage:
    def __init__(self, context: "FakeContext", mode: str) -> None:
        self.context = context
        self.mode = mode
        self.url = PUBLIC_URL
        self.closed = False

    def goto(self, url: str, **_kwargs: Any) -> FakeResponse:
        if self.mode == "timeout":
            raise PlaywrightTimeoutError("timeout")
        initial_route = FakeRoute(FakeRequest(url, navigation=True))
        assert self.context.route_handler is not None
        self.context.route_handler(initial_route)
        if self.mode == "navigation_ssrf":
            unsafe_route = FakeRoute(FakeRequest("http://127.0.0.1/admin", navigation=True))
            self.context.route_handler(unsafe_route)
            assert unsafe_route.aborted is True
            raise PlaywrightError("net::ERR_BLOCKED_BY_CLIENT")
        return FakeResponse()

    def wait_for_load_state(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def content(self) -> str:
        return VALID_HTML

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.route_handler = None
        self.page: FakePage | None = None
        self.closed = False

    def route(self, _pattern: str, handler) -> None:
        self.route_handler = handler

    def route_web_socket(self, _pattern: str, _handler) -> None:
        return None

    def new_page(self) -> FakePage:
        self.page = FakePage(self, self.mode)
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.context: FakeContext | None = None
        self.closed = False

    def new_context(self, **_kwargs: Any) -> FakeContext:
        self.context = FakeContext(self.mode)
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.browser: FakeBrowser | None = None

    def launch(self, **_kwargs: Any) -> FakeBrowser:
        self.browser = FakeBrowser(self.mode)
        return self.browser


class FakePlaywright:
    def __init__(self, mode: str) -> None:
        self.chromium = FakeChromium(mode)


class FakePlaywrightManager:
    def __init__(self, mode: str) -> None:
        self.playwright = FakePlaywright(mode)

    def __enter__(self) -> FakePlaywright:
        return self.playwright

    def __exit__(self, *_args: Any) -> None:
        return None


def fake_browser_fetcher(mode: str) -> tuple[PlaywrightFetcher, FakePlaywrightManager]:
    manager = FakePlaywrightManager(mode)
    fetcher = PlaywrightFetcher(
        navigation_timeout_seconds=1,
        network_idle_timeout_seconds=1,
        user_agent="GistAI-Test/1.0",
        validator=UrlSafetyValidator(
            resolver=lambda _hostname, _port: [PUBLIC_ADDRESS]
        ),
        playwright_factory=lambda: manager,
    )
    return fetcher, manager


def assert_fake_resources_closed(manager: FakePlaywrightManager) -> None:
    browser = manager.playwright.chromium.browser
    assert browser is not None and browser.closed is True
    assert browser.context is not None and browser.context.closed is True
    assert browser.context.page is not None and browser.context.page.closed is True


def test_playwright_timeout_closes_all_resources() -> None:
    fetcher, manager = fake_browser_fetcher("timeout")

    with pytest.raises(FetchTimeoutError, match="Playwright 加载网页超时"):
        fetcher.fetch(PUBLIC_URL)

    assert_fake_resources_closed(manager)


def test_playwright_navigation_ssrf_is_blocked_and_resources_close() -> None:
    fetcher, manager = fake_browser_fetcher("navigation_ssrf")

    with pytest.raises(UnsafeUrlError, match="内部网络"):
        fetcher.fetch(PUBLIC_URL)

    assert_fake_resources_closed(manager)


def test_unsafe_initial_url_does_not_start_playwright() -> None:
    http_fetcher = StubFetcher(error=UnsafeUrlError("禁止访问本机或内部网络地址"))
    browser_fetcher = StubFetcher(error=AssertionError("SSRF URL 不应进入 Playwright"))

    with pytest.raises(UnsafeUrlError):
        crawler_with_stubs(http_fetcher, browser_fetcher).fetch_article(
            "http://127.0.0.1/admin"
        )

    assert browser_fetcher.calls == 0
