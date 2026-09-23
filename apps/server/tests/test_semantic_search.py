import math
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.service import AIService
from app.api.deps import get_ai_service, get_embedding_service
from app.embedding.errors import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingConnectionError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingServiceError,
    EmbeddingTimeoutError,
)
from app.main import app
from app.models.article import Article
from app.models.article_chunk import ArticleChunk
from app.services.search import SearchService


def unit_vector(similarity: float) -> list[float]:
    """构造与第一坐标轴具有指定余弦相似度的 1024 维单位向量。"""

    vector = [0.0] * 1024
    vector[0] = similarity
    vector[1] = math.sqrt(1.0 - similarity**2)
    return vector


class QueryEmbeddingStub:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or unit_vector(1.0)
        self.queries: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return self.vector


class FailedQueryEmbeddingStub:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or EmbeddingTimeoutError("Embedding 请求超时")

    def embed_query(self, _query: str) -> list[float]:
        raise self.error


class InvalidDimensionQueryEmbeddingStub:
    def embed_query(self, _query: str) -> list[float]:
        return [0.1] * 1023


def create_article(
    session: Session,
    *,
    user_id: int = 1,
    title: str | None = None,
    embedding_status: str = "completed",
    status: str = "completed",
) -> Article:
    article = Article(
        user_id=user_id,
        source_type="web",
        source_url=f"https://semantic.example/{uuid4()}",
        source_name="语义测试站点",
        title=title or f"语义测试文章-{uuid4()}",
        clean_content="语义搜索测试正文保持不变。",
        content_hash="a" * 64,
        one_sentence_summary="语义搜索测试摘要。",
        status=status,
        fetch_status="completed",
        ai_status="completed",
        embedding_status=embedding_status,
    )
    session.add(article)
    session.flush()
    return article


def add_chunk(
    session: Session,
    article: Article,
    *,
    index: int,
    similarity: float,
    content: str | None = None,
) -> ArticleChunk:
    chunk = ArticleChunk(
        article_id=article.id,
        chunk_index=index,
        content=content or f"文章 {article.id} 的切片 {index}",
        token_count=10,
        embedding=unit_vector(similarity),
    )
    session.add(chunk)
    session.flush()
    return chunk


def semantic_post(client: TestClient, query: str = "知识系统可靠性", top_k: int = 3):
    return client.post(
        "/api/v1/search/semantic",
        json={"query": query, "top_k": top_k},
    )


def test_query_embedding_pgvector_score_and_result_schema(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(db_session, title="可靠的知识处理系统")
    chunk = add_chunk(
        db_session,
        article,
        index=0,
        similarity=0.8,
        content="通过校验与状态管理提高系统可靠性。",
    )
    db_session.commit()
    embedding = QueryEmbeddingStub()
    app.dependency_overrides[get_embedding_service] = lambda: embedding

    response = semantic_post(client, query="  如何提高系统可靠性？  ")

    assert response.status_code == 200
    assert embedding.queries == ["如何提高系统可靠性？"]
    data = response.json()["data"]
    assert data["top_k"] == 3
    assert data["similarity_threshold"] == 0.35
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["article_id"] == article.id
    assert item["chunk_id"] == chunk.id
    assert item["chunk_index"] == 0
    assert item["excerpt"] == chunk.content
    assert item["score"] == pytest.approx(0.8, abs=1e-6)
    assert "clean_content" not in item


def test_threshold_filters_below_threshold_and_empty_is_success(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(db_session)
    add_chunk(db_session, article, index=0, similarity=0.34)
    db_session.commit()
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    response = semantic_post(client)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_score_desc_top_k_and_stable_order(
    client: TestClient,
    db_session: Session,
) -> None:
    articles = [create_article(db_session) for _ in range(4)]
    similarities = [0.7, 0.9, 0.9, 0.8]
    for article, similarity in zip(articles, similarities, strict=True):
        add_chunk(db_session, article, index=0, similarity=similarity)
    db_session.commit()
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    response = semantic_post(client, top_k=3)

    items = response.json()["data"]["items"]
    assert len(items) == 3
    assert [item["score"] for item in items] == pytest.approx([0.9, 0.9, 0.8])
    tied_ids = sorted([articles[1].id, articles[2].id])
    assert [item["article_id"] for item in items[:2]] == tied_ids


def test_multiple_chunks_keep_only_best_chunk_per_article(
    client: TestClient,
    db_session: Session,
) -> None:
    first = create_article(db_session)
    add_chunk(db_session, first, index=0, similarity=0.7)
    best = add_chunk(db_session, first, index=1, similarity=0.95)
    add_chunk(db_session, first, index=2, similarity=0.8)
    second = create_article(db_session)
    add_chunk(db_session, second, index=0, similarity=0.9)
    db_session.commit()
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    items = semantic_post(client, top_k=3).json()["data"]["items"]

    assert [item["article_id"] for item in items] == [first.id, second.id]
    assert items[0]["chunk_id"] == best.id


def test_user_isolation_and_embedding_status_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    allowed = create_article(db_session, user_id=1)
    add_chunk(db_session, allowed, index=0, similarity=0.7)
    other_user = create_article(db_session, user_id=2)
    add_chunk(db_session, other_user, index=0, similarity=0.99)
    pending = create_article(db_session, user_id=1, embedding_status="processing")
    add_chunk(db_session, pending, index=0, similarity=0.98)
    failed = create_article(db_session, user_id=1, embedding_status="failed")
    add_chunk(db_session, failed, index=0, similarity=0.97)
    db_session.commit()
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    items = semantic_post(client).json()["data"]["items"]

    assert [item["article_id"] for item in items] == [allowed.id]


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_is_rejected(client: TestClient, query: str) -> None:
    response = semantic_post(client, query=query)

    assert response.status_code == 422
    assert response.json()["code"] == 42200


@pytest.mark.parametrize("top_k", [0, 51])
def test_top_k_range_is_restricted(client: TestClient, top_k: int) -> None:
    response = semantic_post(client, top_k=top_k)

    assert response.status_code == 422


def test_embedding_failure_returns_safe_error(client: TestClient) -> None:
    app.dependency_overrides[get_embedding_service] = lambda: FailedQueryEmbeddingStub()

    response = semantic_post(client)

    assert response.status_code == 502
    assert response.json() == {
        "code": 50201,
        "message": "Embedding 请求超时",
        "data": None,
    }
    assert "Traceback" not in response.text
    assert "Authorization" not in response.text


@pytest.mark.parametrize(
    "error",
    [
        EmbeddingConfigurationError("Embedding 配置缺失：EMBEDDING_API_KEY"),
        EmbeddingConnectionError("无法连接 Embedding 服务"),
        EmbeddingAuthenticationError("Embedding 鉴权失败，请检查本机配置"),
        EmbeddingRateLimitError("Embedding 服务请求过于频繁，请稍后重试"),
        EmbeddingServiceError("Embedding 服务暂时不可用"),
        EmbeddingResponseError("Embedding 返回空内容"),
    ],
)
def test_embedding_error_types_are_safely_mapped(
    client: TestClient,
    error: Exception,
) -> None:
    app.dependency_overrides[get_embedding_service] = lambda: FailedQueryEmbeddingStub(
        error
    )

    response = semantic_post(client)

    assert response.status_code == 502
    assert response.json()["message"] == str(error)
    assert "Traceback" not in response.text
    assert "Authorization" not in response.text


def test_query_vector_dimension_is_checked_before_pgvector(client: TestClient) -> None:
    app.dependency_overrides[get_embedding_service] = (
        lambda: InvalidDimensionQueryEmbeddingStub()
    )

    response = semantic_post(client)

    assert response.status_code == 502
    assert response.json()["message"] == "Embedding 向量维度必须为 1024"


def test_database_failure_returns_safe_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    def failed_search(*_args, **_kwargs):
        raise SQLAlchemyError("sensitive database details")

    monkeypatch.setattr(SearchService, "semantic_search", failed_search)
    response = semantic_post(client)

    assert response.status_code == 500
    assert response.json()["message"] == "数据库操作失败"
    assert "sensitive database details" not in response.text
    assert "Traceback" not in response.text


def test_semantic_search_is_read_only_and_does_not_call_llm(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(db_session)
    chunk = add_chunk(db_session, article, index=0, similarity=0.9)
    db_session.commit()
    original = {
        "status": article.status,
        "clean_content": article.clean_content,
        "content_hash": article.content_hash,
        "summary": article.one_sentence_summary,
        "chunk_content": chunk.content,
        "embedding": list(chunk.embedding),
    }
    app.dependency_overrides[get_embedding_service] = lambda: QueryEmbeddingStub()

    def forbidden_llm() -> AIService:
        raise AssertionError("语义搜索不得调用 LLM")

    app.dependency_overrides[get_ai_service] = forbidden_llm
    response = semantic_post(client)

    assert response.status_code == 200
    db_session.expire_all()
    persisted_article = db_session.get(Article, article.id)
    persisted_chunk = db_session.get(ArticleChunk, chunk.id)
    assert persisted_article is not None
    assert persisted_chunk is not None
    assert persisted_article.status == original["status"]
    assert persisted_article.clean_content == original["clean_content"]
    assert persisted_article.content_hash == original["content_hash"]
    assert persisted_article.one_sentence_summary == original["summary"]
    assert persisted_chunk.content == original["chunk_content"]
    assert list(persisted_chunk.embedding) == pytest.approx(original["embedding"])
    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == article.id
        )
    ) == 1


def test_phase9_keyword_search_remains_available(client: TestClient) -> None:
    response = client.get("/api/v1/search/keyword", params={"q": "不存在的关键词"})

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
