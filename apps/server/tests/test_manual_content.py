import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import AIArticleTopicResult
from app.api.deps import get_ai_service, get_crawler_service
from app.core.config import settings
from app.crawler.cleaner import clean_and_validate_content
from app.main import app
from app.models.article import Article
from app.models.tag import Tag


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
    assert data["status"] == "completed"
    assert data["fetch_error"] is None
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "completed"
    assert data["source_type"] == "web"

    persisted = db_session.scalar(select(Article).where(Article.id == article.id))
    assert persisted is not None
    assert persisted.clean_content == expected_content
    assert persisted.content_hash == expected_hash


def test_manual_content_uses_summary_with_owned_topics_mode(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)
    owned = Tag(user_id=1, name=f"手动正式-{uuid4()}", status="active")
    foreign = Tag(user_id=2, name=f"外部正式-{uuid4()}", status="active")
    db_session.add_all([owned, foreign])
    db_session.commit()

    class RecordingTopicAI:
        def __init__(self) -> None:
            self.catalogs: list[list[str]] = []

        def generate_article_summary_with_topics(
            self,
            _content: str,
            active_topic_names: list[str],
        ) -> AIArticleTopicResult:
            self.catalogs.append(active_topic_names)
            return AIArticleTopicResult(
                one_sentence_summary="手动正文摘要",
                key_points=["手动正文同样分类"],
                detailed_summary="手动粘贴正文使用摘要与主题模式。",
                topics=[owned.name],
            )

    ai = RecordingTopicAI()
    app.dependency_overrides[get_ai_service] = lambda: ai

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-content",
        json={"content": MANUAL_CONTENT},
    )

    assert response.status_code == 200
    assert response.json()["data"]["tags"] == [owned.name]
    assert ai.catalogs == [[owned.name]]


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


def test_manual_import_same_url_recovers_original_article(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-import",
        json={"source_url": article.source_url, "content": MANUAL_CONTENT},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == article.id
    assert data["status"] == "completed"
    assert data["fetch_status"] == "completed"
    assert data["source_url"] == article.source_url
    assert db_session.scalar(select(Article.id).where(Article.source_url == article.source_url)) == article.id


def test_manual_import_saves_optional_title_in_detail_and_list(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-import",
        json={
            "source_url": article.source_url,
            "content": MANUAL_CONTENT,
            "title": "  手动填写的标题  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "手动填写的标题"
    detail = client.get(f"/api/v1/articles/{article.id}").json()["data"]
    listed = client.get("/api/v1/articles").json()["data"]["items"]
    assert detail["title"] == "手动填写的标题"
    assert next(item for item in listed if item["id"] == article.id)["title"] == "手动填写的标题"


def test_manual_import_blank_title_does_not_block_content(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-import",
        json={
            "source_url": article.source_url,
            "content": MANUAL_CONTENT,
            "title": "  \t  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] is None
    assert response.json()["data"]["fetch_status"] == "completed"


def test_manual_import_rejects_overlong_title_without_saving_content(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{article.id}/manual-import",
        json={"source_url": article.source_url, "content": MANUAL_CONTENT, "title": "题" * 256},
    )

    assert response.status_code == 422
    db_session.refresh(article)
    assert article.clean_content is None


def test_manual_import_changed_url_creates_article_without_changing_original(
    client: TestClient,
    db_session: Session,
) -> None:
    original = add_article(db_session)
    new_url = f"https://manual.example/new-{uuid4()}"

    response = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"source_url": new_url, "content": MANUAL_CONTENT, "title": "新链接的手动标题"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] != original.id
    assert data["source_url"] == new_url
    assert data["title"] == "新链接的手动标题"
    assert data["status"] == "completed"
    db_session.refresh(original)
    assert original.status == "failed"
    assert original.clean_content is None
    assert original.fetch_error == "普通 HTTP 与 Playwright 均失败"
    assert original.title is None


def test_manual_title_survives_continued_and_regenerated_processing(
    client: TestClient,
    db_session: Session,
) -> None:
    article = add_article(db_session)
    imported = client.post(
        f"/api/v1/articles/{article.id}/manual-import",
        json={"source_url": article.source_url, "content": MANUAL_CONTENT, "title": "手动标题"},
    )
    assert imported.status_code == 200

    article.status = "partial_failed"
    article.ai_status = "failed"
    article.embedding_status = "pending"
    db_session.commit()
    continued = client.post(f"/api/v1/articles/{article.id}/reprocess")
    assert continued.status_code == 200
    assert continued.json()["data"]["article"]["title"] == "手动标题"

    for endpoint in ("regenerate-ai", "regenerate-embedding"):
        regenerated = client.post(f"/api/v1/articles/{article.id}/{endpoint}")
        assert regenerated.status_code == 200
        assert regenerated.json()["data"]["title"] == "手动标题"

    db_session.refresh(article)
    assert article.title == "手动标题"


def test_manual_import_duplicate_url_returns_existing_id_without_overwriting(
    client: TestClient,
    db_session: Session,
) -> None:
    original = add_article(db_session)
    existing = add_article(db_session)

    response = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"source_url": existing.source_url, "content": MANUAL_CONTENT},
    )

    assert response.status_code == 409
    assert response.json()["data"]["article_id"] == existing.id
    db_session.refresh(existing)
    assert existing.clean_content is None
    db_session.refresh(original)
    assert original.clean_content is None


def test_manual_import_rejects_invalid_content_and_existing_valid_content(
    client: TestClient,
    db_session: Session,
) -> None:
    original = add_article(db_session)
    new_url = f"https://manual.example/new-{uuid4()}"
    invalid = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"source_url": new_url, "content": "太短"},
    )
    assert invalid.status_code == 422
    assert db_session.scalar(select(Article.id).where(Article.source_url == new_url)) is None

    old_content = "已有有效正文。" * 40
    original.clean_content = old_content
    original.status = "partial_failed"
    db_session.commit()
    rejected = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"source_url": original.source_url, "content": MANUAL_CONTENT},
    )
    assert rejected.status_code == 409
    db_session.refresh(original)
    assert original.clean_content == old_content


def test_manual_import_requires_url_and_rejects_processing_record(
    client: TestClient,
    db_session: Session,
) -> None:
    original = add_article(db_session)
    missing_url = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"content": MANUAL_CONTENT},
    )
    assert missing_url.status_code == 422

    original.status = "processing"
    db_session.commit()
    processing = client.post(
        f"/api/v1/articles/{original.id}/manual-import",
        json={"source_url": original.source_url, "content": MANUAL_CONTENT},
    )
    assert processing.status_code == 409
    assert processing.json()["code"] == 40903
    db_session.refresh(original)
    assert original.clean_content is None
