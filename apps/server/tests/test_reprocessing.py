import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import LLMResponseError, LLMTimeoutError
from app.ai.schemas import AIArticleResult
from app.api.deps import get_ai_service, get_crawler_service, get_embedding_service
from app.crawler.errors import CrawlerFallbackError
from app.crawler.extractor import ExtractedArticle
from app.embedding.errors import EmbeddingResponseError, EmbeddingTimeoutError
from app.embedding.schemas import EmbeddedChunk
from app.main import app
from app.models.article import Article
from app.models.article_chunk import ArticleChunk
from app.models.article_tag import ArticleTag
from app.models.tag import Tag


OLD_CONTENT = "旧的有效正文用于验证重新处理时的数据保护和原子替换。" * 20
NEW_CONTENT = "新的有效正文包含更新后的知识，并用于重新生成摘要和向量。" * 20


class CrawlerStub:
    def __init__(self, content: str = NEW_CONTENT, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    def fetch_article(self, _url: str) -> ExtractedArticle:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ExtractedArticle(
            clean_content=self.content,
            title="重新提取的标题",
            source_name="重新提取站点",
        )


class AIStub:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.contents: list[str] = []

    def generate_article_result(self, content: str) -> AIArticleResult:
        self.calls += 1
        self.contents.append(content)
        if self.error is not None:
            raise self.error
        return AIArticleResult(
            one_sentence_summary="新的摘要",
            key_points=["新观点一", "新观点二"],
            detailed_summary="新的详细摘要",
            tags=["新标签", "共同标签"],
        )


class EmbeddingStub:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.contents: list[str] = []

    def generate(self, content: str) -> list[EmbeddedChunk]:
        self.calls += 1
        self.contents.append(content)
        if self.error is not None:
            raise self.error
        midpoint = len(content) // 2
        return [
            EmbeddedChunk(
                chunk_index=index,
                content=value,
                token_count=30 + index,
                embedding=[0.1 + index / 10] * 1024,
                metadata={"generation": "new", "index": index},
            )
            for index, value in enumerate([content[:midpoint], content[midpoint:]])
        ]


class ExplodingService:
    def __getattr__(self, name: str):
        raise AssertionError(f"不应调用 {name}")


def create_completed_article(
    session: Session,
    *,
    user_id: int = 1,
    source_url: str | None = None,
    status: str = "completed",
    fetch_status: str = "completed",
    ai_status: str = "completed",
    embedding_status: str = "completed",
) -> Article:
    article = Article(
        user_id=user_id,
        source_type="web",
        source_url=source_url or f"https://reprocess.example/{uuid4()}",
        title="用户保留的标题",
        clean_content=OLD_CONTENT,
        content_hash=hashlib.sha256(OLD_CONTENT.encode()).hexdigest(),
        one_sentence_summary="旧摘要",
        key_points=["旧观点"],
        detailed_summary="旧详细摘要",
        status=status,
        fetch_status=fetch_status,
        ai_status=ai_status,
        embedding_status=embedding_status,
    )
    session.add(article)
    session.flush()
    old_tag = Tag(user_id=user_id, name=f"旧标签-{uuid4()}")
    common_tag = Tag(user_id=user_id, name="共同标签")
    session.add_all([old_tag, common_tag])
    session.flush()
    session.add_all(
        [
            ArticleTag(article_id=article.id, tag_id=old_tag.id),
            ArticleTag(article_id=article.id, tag_id=common_tag.id),
            ArticleChunk(
                article_id=article.id,
                chunk_index=0,
                content="旧切片",
                token_count=10,
                embedding=[0.5] * 1024,
                chunk_metadata={"generation": "old"},
            ),
        ]
    )
    session.commit()
    session.refresh(article)
    return article


def article_values(article: Article) -> tuple:
    return (
        article.id,
        article.clean_content,
        article.content_hash,
        article.title,
        article.one_sentence_summary,
        tuple(article.key_points or []),
        article.detailed_summary,
    )


def tag_names(session: Session, article_id: int) -> list[str]:
    return list(
        session.scalars(
            select(Tag.name)
            .join(ArticleTag, ArticleTag.tag_id == Tag.id)
            .where(ArticleTag.article_id == article_id)
            .order_by(Tag.name)
        ).all()
    )


def chunks(session: Session, article_id: int) -> list[ArticleChunk]:
    return list(
        session.scalars(
            select(ArticleChunk)
            .where(ArticleChunk.article_id == article_id)
            .order_by(ArticleChunk.chunk_index)
        ).all()
    )


def configure(crawler=None, ai=None, embedding=None) -> None:
    if crawler is not None:
        app.dependency_overrides[get_crawler_service] = lambda: crawler
    if ai is not None:
        app.dependency_overrides[get_ai_service] = lambda: ai
    if embedding is not None:
        app.dependency_overrides[get_embedding_service] = lambda: embedding


def test_reprocess_success_atomically_replaces_complete_pipeline(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    original_id = article.id
    crawler, ai, embedding = CrawlerStub(), AIStub(), EmbeddingStub()
    configure(crawler, ai, embedding)

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content_unchanged"] is False
    result = data["article"]
    assert result["id"] == original_id
    assert result["clean_content"] == NEW_CONTENT
    assert result["content_hash"] == hashlib.sha256(NEW_CONTENT.encode()).hexdigest()
    assert result["one_sentence_summary"] == "新的摘要"
    assert set(result["tags"]) == {"新标签", "共同标签"}
    assert result["status"] == "completed"
    assert result["fetch_status"] == "completed"
    assert result["ai_status"] == "completed"
    assert result["embedding_status"] == "completed"
    current_chunks = chunks(db_session, article.id)
    assert [chunk.chunk_index for chunk in current_chunks] == [0, 1]
    assert all(chunk.chunk_metadata["generation"] == "new" for chunk in current_chunks)
    assert crawler.calls == ai.calls == embedding.calls == 1


def test_reprocess_fetch_failure_preserves_all_old_data(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    old_chunks = chunks(db_session, article.id)
    crawler = CrawlerStub(error=CrawlerFallbackError("HTTP 与 Playwright 均失败"))
    ai, embedding = AIStub(), EmbeddingStub()
    configure(crawler, ai, embedding)

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    current_chunks = chunks(db_session, article.id)
    assert [(c.content, c.embedding[0]) for c in current_chunks] == [
        (old_chunks[0].content, old_chunks[0].embedding[0])
    ]
    assert article.fetch_status == "failed"
    assert article.fetch_error == "HTTP 与 Playwright 均失败"
    assert article.ai_status == "completed"
    assert article.embedding_status == "completed"
    assert article.status == "partial_failed"
    assert ai.calls == embedding.calls == 0


def test_reprocess_ai_failure_preserves_old_ai_content_tags_and_chunks(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    old_chunk = chunks(db_session, article.id)[0]
    ai = AIStub(LLMTimeoutError("LLM 请求超时"))
    embedding = EmbeddingStub()
    configure(CrawlerStub(), ai, embedding)

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    assert chunks(db_session, article.id)[0].content == old_chunk.content
    assert article.fetch_status == "completed"
    assert article.ai_status == "failed"
    assert article.ai_error == "LLM 请求超时"
    assert article.embedding_status == "completed"
    assert article.status == "partial_failed"
    assert embedding.calls == 0


def test_reprocess_embedding_failure_preserves_all_old_business_data(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    old_chunk = chunks(db_session, article.id)[0]
    embedding = EmbeddingStub(EmbeddingTimeoutError("Embedding 请求超时"))
    configure(CrawlerStub(), AIStub(), embedding)

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    assert chunks(db_session, article.id)[0].content == old_chunk.content
    assert article.fetch_status == "completed"
    assert article.ai_status == "completed"
    assert article.embedding_status == "failed"
    assert article.embedding_error == "Embedding 请求超时"
    assert article.status == "partial_failed"


def test_reprocess_embedding_failure_restores_previous_failed_ai_state(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(
        db_session,
        status="partial_failed",
        ai_status="failed",
    )
    article.ai_error = "旧 AI 错误"
    article.one_sentence_summary = None
    article.key_points = None
    article.detailed_summary = None
    db_session.commit()
    configure(
        CrawlerStub(),
        AIStub(),
        EmbeddingStub(EmbeddingTimeoutError("Embedding 请求超时")),
    )

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article.ai_status == "failed"
    assert article.ai_error == "旧 AI 错误"
    assert article.one_sentence_summary is None
    assert article.embedding_status == "failed"
    assert article.status == "partial_failed"


def test_reprocess_unchanged_hash_skips_ai_and_embedding(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(
        db_session,
        status="partial_failed",
        fetch_status="failed",
    )
    crawler = CrawlerStub(content=OLD_CONTENT)
    ai, embedding = AIStub(), EmbeddingStub()
    configure(crawler, ai, embedding)

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 200
    assert response.json()["data"]["content_unchanged"] is True
    assert "正文未变化" in response.json()["message"]
    db_session.refresh(article)
    assert article.status == "completed"
    assert article.fetch_status == "completed"
    assert ai.calls == embedding.calls == 0


def test_reprocess_recovers_partial_failed_article(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(
        db_session,
        status="partial_failed",
        ai_status="failed",
        embedding_status="failed",
    )
    configure(CrawlerStub(), AIStub(), EmbeddingStub())

    data = client.post(f"/api/v1/articles/{article.id}/reprocess").json()["data"][
        "article"
    ]

    assert data["status"] == "completed"
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "completed"
    assert data["ai_error"] is None
    assert data["embedding_error"] is None


def test_regenerate_ai_only_replaces_ai_and_tags(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_content_hash = (article.clean_content, article.content_hash)
    old_chunks = [(c.content, list(c.embedding)) for c in chunks(db_session, article.id)]
    ai = AIStub()
    configure(ExplodingService(), ai, ExplodingService())

    response = client.post(f"/api/v1/articles/{article.id}/regenerate-ai")

    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["clean_content"], data["content_hash"]) == old_content_hash
    assert data["one_sentence_summary"] == "新的摘要"
    assert set(data["tags"]) == {"新标签", "共同标签"}
    assert data["embedding_status"] == "completed"
    assert data["status"] == "completed"
    current_chunks = [(c.content, list(c.embedding)) for c in chunks(db_session, article.id)]
    assert current_chunks == old_chunks
    assert ai.calls == 1


def test_regenerate_ai_failure_preserves_old_ai_tags_and_embedding(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    old_chunk = chunks(db_session, article.id)[0]
    configure(
        ExplodingService(),
        AIStub(LLMResponseError("LLM 返回的结构化结果无效")),
        ExplodingService(),
    )

    response = client.post(f"/api/v1/articles/{article.id}/regenerate-ai")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    assert chunks(db_session, article.id)[0].content == old_chunk.content
    assert article.ai_status == "failed"
    assert article.ai_error == "LLM 返回的结构化结果无效"
    assert article.embedding_status == "completed"
    assert article.status == "partial_failed"


def test_regenerate_ai_recovers_failed_stage_without_polluting_embedding(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(
        db_session,
        status="partial_failed",
        ai_status="failed",
    )
    configure(ai=AIStub())

    data = client.post(f"/api/v1/articles/{article.id}/regenerate-ai").json()["data"]

    assert data["status"] == "completed"
    assert data["ai_status"] == "completed"
    assert data["embedding_status"] == "completed"


def test_regenerate_embedding_only_replaces_chunks(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    embedding = EmbeddingStub()
    configure(ExplodingService(), ExplodingService(), embedding)

    response = client.post(f"/api/v1/articles/{article.id}/regenerate-embedding")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    current_chunks = chunks(db_session, article.id)
    assert [c.chunk_index for c in current_chunks] == [0, 1]
    assert [c.embedding[0] for c in current_chunks] == pytest.approx([0.1, 0.2])
    assert article.embedding_status == "completed"
    assert article.status == "completed"
    assert embedding.calls == 1


def test_regenerate_embedding_failure_preserves_old_chunks_and_ai(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session)
    old_values = article_values(article)
    old_tags = tag_names(db_session, article.id)
    old_chunks = [(c.content, list(c.embedding)) for c in chunks(db_session, article.id)]
    embedding = EmbeddingStub(EmbeddingResponseError("Embedding 返回数量错误"))
    configure(ExplodingService(), ExplodingService(), embedding)

    response = client.post(f"/api/v1/articles/{article.id}/regenerate-embedding")

    assert response.status_code == 200
    db_session.refresh(article)
    assert article_values(article) == old_values
    assert tag_names(db_session, article.id) == old_tags
    assert [(c.content, list(c.embedding)) for c in chunks(db_session, article.id)] == old_chunks
    assert article.embedding_status == "failed"
    assert article.embedding_error == "Embedding 返回数量错误"
    assert article.status == "partial_failed"


def test_regenerate_embedding_recovers_failed_stage(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(
        db_session,
        status="partial_failed",
        embedding_status="failed",
    )
    configure(embedding=EmbeddingStub())

    data = client.post(
        f"/api/v1/articles/{article.id}/regenerate-embedding"
    ).json()["data"]

    assert data["status"] == "completed"
    assert data["embedding_status"] == "completed"
    assert data["ai_status"] == "completed"


@pytest.mark.parametrize("endpoint", ["regenerate-ai", "regenerate-embedding"])
def test_regeneration_rejects_missing_or_short_content(
    client: TestClient,
    db_session: Session,
    endpoint: str,
) -> None:
    article = create_completed_article(db_session)
    article.clean_content = "过短正文"
    article.content_hash = hashlib.sha256(article.clean_content.encode()).hexdigest()
    db_session.commit()

    response = client.post(f"/api/v1/articles/{article.id}/{endpoint}")

    assert response.status_code == 422
    assert response.json()["code"] == 42203


@pytest.mark.parametrize("endpoint", ["reprocess", "regenerate-ai", "regenerate-embedding"])
def test_processing_article_returns_409(
    client: TestClient,
    db_session: Session,
    endpoint: str,
) -> None:
    article = create_completed_article(
        db_session,
        status="processing",
        ai_status="processing",
    )

    response = client.post(f"/api/v1/articles/{article.id}/{endpoint}")

    assert response.status_code == 409
    assert response.json()["code"] == 40903


@pytest.mark.parametrize("endpoint", ["reprocess", "regenerate-ai", "regenerate-embedding"])
def test_reprocessing_endpoints_return_404_for_missing_or_other_user(
    client: TestClient,
    db_session: Session,
    endpoint: str,
) -> None:
    other = create_completed_article(db_session, user_id=2)

    missing = client.post(f"/api/v1/articles/9223372036854775807/{endpoint}")
    isolated = client.post(f"/api/v1/articles/{other.id}/{endpoint}")

    assert missing.status_code == 404
    assert isolated.status_code == 404


def test_reprocess_rejects_article_without_fetchable_url(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_completed_article(db_session, source_url="manual-content-only")

    response = client.post(f"/api/v1/articles/{article.id}/reprocess")

    assert response.status_code == 422
    assert response.json()["code"] == 42204


@pytest.mark.parametrize(
    ("endpoint", "service_name"),
    [
        ("reprocess", "crawler"),
        ("regenerate-ai", "ai"),
        ("regenerate-embedding", "embedding"),
    ],
)
def test_unexpected_external_errors_are_safe(
    client: TestClient,
    db_session: Session,
    endpoint: str,
    service_name: str,
) -> None:
    article = create_completed_article(db_session)

    class UnexpectedCrawler:
        def fetch_article(self, _url: str):
            raise RuntimeError("private provider detail")

    class UnexpectedAI:
        def generate_article_result(self, _content: str):
            raise RuntimeError("private provider detail")

    class UnexpectedEmbedding:
        def generate(self, _content: str):
            raise RuntimeError("private provider detail")

    configure(
        UnexpectedCrawler() if service_name == "crawler" else CrawlerStub(),
        UnexpectedAI() if service_name == "ai" else AIStub(),
        UnexpectedEmbedding() if service_name == "embedding" else EmbeddingStub(),
    )

    response = client.post(f"/api/v1/articles/{article.id}/{endpoint}")

    assert response.status_code == 200
    assert "private provider detail" not in response.text
    assert "Traceback" not in response.text
