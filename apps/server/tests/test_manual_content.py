import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_crawler_service
from app.core.config import settings
from app.crawler.cleaner import clean_and_validate_content
from app.main import app
from app.models.article import Article


MIN_CONTENT_CHARS = settings.fetch_min_content_chars
MANUAL_CONTENT = (
    "\u200b  这是用户手动提交的文章正文，用于验证清洗、有效性校验、哈希计算和状态恢复。  "
    * 12
    + "\n\n\n\n第二个段落用于验证多余空行会被清理。"
)


def add_article(
    db_session: Session,
    *,
    clean_content: str | None = None,
    content_hash: str | None = None,
    status: str = "failed",
    fetch_status: str = "failed",
    fetch_error: str | None = "普通 HTTP 与 Playwright 均失败",
) -> Article:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://manual.example/{uuid4()}",
        clean_content=clean_content,
        content_hash=content_hash,
        status=status,
        fetch_status=fetch_status,
        fetch_error=fetch_error,
        ai_status="pending",
        embedding_status="pending",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    return article


def test_failed_article_accepts_manual_content_and_persists_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": MANUAL_CONTENT},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    expected_content = clean_and_validate_content(MANUAL_CONTENT, MIN_CONTENT_CHARS)
    expected_hash = hashlib.sha256(expected_content.encode("utf-8")).hexdigest()
    assert body["message"] == "手动正文保存成功"
    assert data["clean_content"] == expected_content
    assert data["content_hash"] == expected_hash
    assert data["fetch_status"] == "completed"
    assert data["status"] == "processing"
    assert data["fetch_error"] is None
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "pending"
    assert data["source_type"] == "web"

    persisted = db_session.scalar(select(Article).where(Article.id == article.id))
    assert persisted is not None
    assert persisted.clean_content == expected_content
    assert persisted.content_hash == expected_hash


def test_manual_content_article_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/articles/9223372036854775807/manual-content",
        json={"content": MANUAL_CONTENT},
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Article 不存在"


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        ("", 42200),
        ("   \n\t\u200b  ", 42202),
        ("清洗后仍然太短", 42202),
    ],
)
def test_manual_content_rejects_empty_whitespace_and_short_text(
    client: TestClient,
    db_session: Session,
    content: str,
    expected_code: int,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": content},
    )

    assert response.status_code == 422
    assert response.json()["code"] == expected_code
    persisted = db_session.scalar(select(Article).where(Article.id == article.id))
    assert persisted is not None
    assert persisted.clean_content is None
    assert persisted.content_hash is None
    assert persisted.fetch_status == "failed"


def test_invalid_manual_content_does_not_overwrite_existing_content(
    client: TestClient,
    db_session: Session,
) -> None:
    old_content = "已有的有效正文。" * 40
    old_hash = hashlib.sha256(old_content.encode("utf-8")).hexdigest()
    article = add_article(
        db_session,
        clean_content=old_content,
        content_hash=old_hash,
        status="processing",
        fetch_status="completed",
        fetch_error=None,
    )

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": "无效短正文"},
    )

    assert response.status_code == 422
    db_session.refresh(article)
    assert article.clean_content == old_content
    assert article.content_hash == old_hash
    assert article.fetch_status == "completed"
    assert article.status == "processing"


def test_valid_manual_content_replaces_existing_content(
    client: TestClient,
    db_session: Session,
) -> None:
    old_content = "旧正文。" * 60
    old_hash = hashlib.sha256(old_content.encode("utf-8")).hexdigest()
    article = add_article(
        db_session,
        clean_content=old_content,
        content_hash=old_hash,
        status="processing",
        fetch_status="completed",
        fetch_error=None,
    )

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": MANUAL_CONTENT},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["clean_content"] != old_content
    assert data["content_hash"] != old_hash
    db_session.refresh(article)
    assert article.clean_content == data["clean_content"]
    assert article.content_hash == data["content_hash"]


def test_manual_content_does_not_call_http_or_playwright(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    class ExplodingCrawler:
        calls = 0

        def fetch_article(self, _url: str) -> None:
            self.calls += 1
            raise AssertionError("manual-content 不应调用 HttpFetcher 或 Playwright")

    crawler = ExplodingCrawler()
    app.dependency_overrides[get_crawler_service] = lambda: crawler

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": MANUAL_CONTENT},
    )

    assert response.status_code == 200
    assert crawler.calls == 0
