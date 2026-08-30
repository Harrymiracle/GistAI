import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_crawler_service
from app.crawler.errors import (
    ExtractionError,
    FetchConnectionError,
    FetchHttpError,
    FetchTimeoutError,
    UnsafeUrlError,
)
from app.crawler.extractor import ArticleExtractor
from app.crawler.http_fetcher import HttpFetcher, UrlSafetyValidator
from app.crawler.service import CrawlerService
from app.main import app
from app.models.article import Article


PUBLIC_URL = "https://public.example/article"
PUBLIC_ADDRESS = "93.184.216.34"
LONG_PARAGRAPH = "这是一段用于验证正文提取、文本清洗和数据库持久化的普通网页文章内容。" * 12


def public_validator() -> UrlSafetyValidator:
    return UrlSafetyValidator(resolver=lambda _hostname, _port: [PUBLIC_ADDRESS])


def mock_crawler(
    handler,
    *,
    min_content_chars: int = 100,
) -> CrawlerService:
    return CrawlerService(
        fetcher=HttpFetcher(
            timeout_seconds=1,
            max_redirects=3,
            user_agent="GistAI-Test/1.0",
            validator=public_validator(),
            transport=httpx.MockTransport(handler),
        ),
        extractor=ArticleExtractor(min_content_chars=min_content_chars),
    )


def article_html() -> str:
    return f"""
    <html>
      <head>
        <title>网页标题</title>
        <meta property="og:site_name" content="示例站点">
        <meta property="article:published_time" content="2025-01-02T03:04:05+00:00">
        <meta name="author" content="测试作者">
      </head>
      <body>
        <nav>导航菜单</nav>
        <article><h1>网页标题</h1><p>{LONG_PARAGRAPH}</p></article>
        <footer>页脚信息</footer>
      </body>
    </html>
    """


def test_http_fetch_extract_and_persist_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    observed_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers.append(request.headers["user-agent"])
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=article_html(),
        )

    app.dependency_overrides[get_crawler_service] = lambda: mock_crawler(handler)
    response = client.post(
        "/api/v1/articles",
        json={"source_url": PUBLIC_URL, "source_type": "web"},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["fetch_status"] == "completed"
    assert data["status"] == "completed"
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "completed"
    assert data["fetch_error"] is None
    assert data["title"] == "网页标题"
    assert data["source_name"] == "示例站点"
    assert len(data["clean_content"]) >= 100
    assert data["content_hash"] == hashlib.sha256(
        data["clean_content"].encode("utf-8")
    ).hexdigest()
    assert observed_headers == ["GistAI-Test/1.0"]

    persisted = db_session.scalar(select(Article).where(Article.id == data["id"]))
    assert persisted is not None
    assert persisted.clean_content == data["clean_content"]
    assert persisted.content_hash == data["content_hash"]


def test_extractor_removes_page_noise_and_cleans_content() -> None:
    result = ArticleExtractor(min_content_chars=100).extract(article_html(), PUBLIC_URL)

    assert LONG_PARAGRAPH[:30] in result.clean_content
    assert "导航菜单" not in result.clean_content
    assert "页脚信息" not in result.clean_content
    assert result.title == "网页标题"
    assert result.published_at is not None


@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (httpx.ConnectTimeout("timeout"), FetchTimeoutError),
        (httpx.ConnectError("connection failed"), FetchConnectionError),
    ],
)
def test_fetch_network_errors_are_safe(raised_error: Exception, expected_error: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(raised_error, httpx.RequestError):
            raised_error.request = request
        raise raised_error

    crawler = mock_crawler(handler)
    with pytest.raises(expected_error):
        crawler.fetch_article(PUBLIC_URL)


@pytest.mark.parametrize("status_code", [403, 404, 500])
def test_fetch_http_errors(status_code: int) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="error")

    with pytest.raises(FetchHttpError, match=str(status_code)):
        mock_crawler(handler).fetch_article(PUBLIC_URL)


def test_extraction_rejects_short_content() -> None:
    short_html = "<html><body><article><p>内容太短</p></article></body></html>"

    with pytest.raises(ExtractionError, match="正文"):
        ArticleExtractor(min_content_chars=100).extract(short_html, PUBLIC_URL)


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://10.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
    ],
)
def test_ssrf_rejects_local_and_internal_addresses(unsafe_url: str) -> None:
    validator = UrlSafetyValidator()

    with pytest.raises(UnsafeUrlError):
        validator.validate(unsafe_url)


def test_ssrf_rejects_domain_resolving_to_private_address() -> None:
    validator = UrlSafetyValidator(resolver=lambda _hostname, _port: ["192.168.1.10"])

    with pytest.raises(UnsafeUrlError):
        validator.validate("https://internal.example/article")


def test_redirect_cannot_bypass_ssrf_validation() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(UnsafeUrlError):
        mock_crawler(handler).fetch_article(PUBLIC_URL)
    assert requested_urls == [PUBLIC_URL]


def test_public_redirect_is_followed() -> None:
    redirected_url = "https://public.example/final"
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == PUBLIC_URL:
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=article_html(),
        )

    result = mock_crawler(handler).fetch_article(PUBLIC_URL)

    assert len(result.clean_content) >= 100
    assert requested_urls == [PUBLIC_URL, redirected_url]


def test_fetch_failure_keeps_article_and_updates_status(
    client: TestClient,
    db_session: Session,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    app.dependency_overrides[get_crawler_service] = lambda: mock_crawler(handler)
    response = client.post(
        "/api/v1/articles",
        json={
            "source_url": "https://public.example/timeout",
            "source_type": "web",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["fetch_status"] == "failed"
    assert data["fetch_error"] == "网页请求超时"
    assert data["clean_content"] is None
    assert data["content_hash"] is None
    assert data["ai_status"] == "pending"
    assert data["embedding_status"] == "pending"
    assert db_session.scalar(select(Article.id).where(Article.id == data["id"])) == data["id"]

    status_response = client.get(f"/api/v1/articles/{data['id']}/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["fetch_error"] == "网页请求超时"


def test_short_content_keeps_article_and_marks_fetch_failed(
    client: TestClient,
    db_session: Session,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><article><p>内容太短</p></article></body></html>",
        )

    app.dependency_overrides[get_crawler_service] = lambda: mock_crawler(handler)
    response = client.post(
        "/api/v1/articles",
        json={
            "source_url": "https://public.example/short",
            "source_type": "web",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["fetch_status"] == "failed"
    assert "正文" in data["fetch_error"]
    assert db_session.scalar(select(Article.id).where(Article.id == data["id"])) == data["id"]
