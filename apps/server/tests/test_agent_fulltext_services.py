from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.agent.article_content import ArticleContentService
from app.agent.fulltext import FullTextEvidenceSelector
from app.agent.web_page_fetch import WebPageFetchService, WebPageValidationError
from app.crawler.errors import FetchConnectionError, UnsafeUrlError
from app.crawler.extractor import ArticleExtractor, ExtractedArticle
from app.crawler.http_fetcher import FetchResult
from app.crawler.service import CrawlerService
from app.embedding.chunker import TokenChunker
from app.models.article import Article


class CrawlerStub:
    def __init__(self, result: ExtractedArticle) -> None:
        self.result = result
        self.urls: list[str] = []

    def fetch_article(self, url: str) -> ExtractedArticle:
        self.urls.append(url)
        return self.result


class ErrorCrawlerStub:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def fetch_article(self, _url: str) -> ExtractedArticle:
        raise self.error


class FetcherStub:
    def __init__(
        self,
        result: FetchResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, _url: str) -> FetchResult:
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def _article(*, user_id: int, content: str | None = None) -> Article:
    return Article(
        user_id=user_id,
        source_type="web",
        source_url=f"https://article.example/{uuid4()}",
        title="测试文章",
        author="作者",
        published_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        clean_content=content,
        status="completed",
        fetch_status="completed",
        ai_status="completed",
        embedding_status="completed",
    )


def test_article_content_service_reads_only_current_user(
    db_session: Session,
) -> None:
    own = _article(user_id=1, content="当前用户的正文")
    other = _article(user_id=2, content="其他用户的秘密正文")
    db_session.add_all([own, other])
    db_session.commit()

    service = ArticleContentService(session=db_session, user_id=1)

    result = service.get(own.id)
    unavailable = service.get(other.id)

    assert result is not None
    assert result.article_id == own.id
    assert result.clean_content == "当前用户的正文"
    assert unavailable is None


def test_article_content_service_treats_missing_content_as_unavailable(
    db_session: Session,
) -> None:
    article = _article(user_id=1, content=None)
    db_session.add(article)
    db_session.commit()

    assert ArticleContentService(session=db_session, user_id=1).get(article.id) is None


def test_web_page_fetch_service_reuses_crawler_pipeline() -> None:
    published_at = datetime(2026, 2, 3, tzinfo=timezone.utc)
    crawler = CrawlerStub(
        ExtractedArticle(
            clean_content="网页完整正文",
            title="网页标题",
            author="网页作者",
            published_at=published_at,
            source_name="示例站点",
        )
    )

    result = WebPageFetchService(crawler).fetch("https://public.example/page")

    assert crawler.urls == ["https://public.example/page"]
    assert result.url == "https://public.example/page"
    assert result.clean_content == "网页完整正文"
    assert result.source == "示例站点"
    assert result.published_at == published_at


def test_web_page_fetch_service_preserves_crawler_ssrf_rejection() -> None:
    service = WebPageFetchService(
        ErrorCrawlerStub(UnsafeUrlError("禁止访问本机地址"))  # type: ignore[arg-type]
    )

    with pytest.raises(WebPageValidationError, match="不可访问"):
        service.fetch("http://127.0.0.1/admin")


def test_web_page_fetch_service_keeps_http_to_playwright_fallback() -> None:
    body = "浏览器渲染后得到的正文内容。" * 30
    html = f"<html><body><article><p>{body}</p></article></body></html>"
    http = FetcherStub(error=FetchConnectionError("HTTP 失败"))
    browser = FetcherStub(
        result=FetchResult(
            html=html,
            final_url="https://public.example/page",
        )
    )
    crawler = CrawlerService(
        fetcher=http,  # type: ignore[arg-type]
        extractor=ArticleExtractor(min_content_chars=100),
        browser_fetcher=browser,  # type: ignore[arg-type]
    )

    result = WebPageFetchService(crawler).fetch("https://public.example/page")

    assert http.calls == 1
    assert browser.calls == 1
    assert body[:20] in result.clean_content


def test_fulltext_selector_prioritizes_relevant_chunks_and_obeys_budget() -> None:
    chunker = TokenChunker(chunk_size=30, overlap=0)
    selector = FullTextEvidenceSelector(chunker=chunker, max_context_tokens=45)
    noise = "无关背景材料。" * 100
    relevant = "Agent Memory checkpoint persistence 是问题的关键答案。" * 4

    article_evidence, web_evidence = selector.select(
        query="Agent Memory checkpoint persistence",
        article_contents=[
            {
                "article_id": 7,
                "title": "长文章",
                "clean_content": noise + relevant + noise,
            }
        ],
        web_page_contents=[],
    )

    assert web_evidence == []
    assert article_evidence
    assert sum(item["token_count"] for item in article_evidence) <= 45
    assert any("checkpoint" in item["content"] for item in article_evidence)
    assert len("".join(item["content"] for item in article_evidence)) < len(noise + relevant + noise)


def test_fulltext_selector_shares_one_budget_across_article_and_web() -> None:
    chunker = TokenChunker(chunk_size=20, overlap=0)
    selector = FullTextEvidenceSelector(chunker=chunker, max_context_tokens=30)

    article_evidence, web_evidence = selector.select(
        query="目标信息",
        article_contents=[
            {"article_id": 1, "title": "文章", "clean_content": "目标信息。" * 30}
        ],
        web_page_contents=[
            {
                "url": "https://public.example/page",
                "title": "网页",
                "source": "示例站点",
                "published_at": None,
                "clean_content": "目标信息。" * 30,
            }
        ],
    )

    assert sum(
        item["token_count"] for item in article_evidence + web_evidence
    ) <= 30
