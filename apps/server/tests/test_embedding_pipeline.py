from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.errors import LLMResponseError
from app.api.deps import get_ai_service, get_embedding_service
from app.embedding.client import OpenAICompatibleEmbeddingClient
from app.embedding.errors import (
    EmbeddingResponseError,
    EmbeddingTimeoutError,
)
from app.embedding.schemas import EmbeddedChunk
from app.embedding.service import EmbeddingService
from app.embedding.chunker import TokenChunker
from app.main import app
from app.models.article import Article
from app.models.article_chunk import ArticleChunk
from app.services.article import ArticleService
from pydantic import SecretStr


def create_payload() -> dict[str, str]:
    return {
        "source_url": f"https://embedding-pipeline.example/{uuid4()}",
        "source_type": "web",
    }


class MultiChunkEmbeddingStub:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, clean_content: str) -> list[EmbeddedChunk]:
        self.calls += 1
        midpoint = len(clean_content) // 2
        contents = [clean_content[:midpoint], clean_content[midpoint:]]
        return [
            EmbeddedChunk(
                chunk_index=index,
                content=content,
                token_count=20 + index,
                embedding=[float(index + 1) / 10] * 1024,
                metadata={"tokenizer": "unit-test", "position": index},
            )
            for index, content in enumerate(contents)
        ]


class ErrorEmbeddingStub:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def generate(self, _clean_content: str) -> list[EmbeddedChunk]:
        self.calls += 1
        raise self.error


def test_embedding_success_persists_ordered_chunks_and_vectors(
    client: TestClient,
    db_session: Session,
) -> None:
    service = MultiChunkEmbeddingStub()
    app.dependency_overrides[get_embedding_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["embedding_status"] == "completed"
    assert data["embedding_error"] is None
    assert data["status"] == "completed"
    assert data["fetch_status"] == "completed"
    assert data["ai_status"] == "completed"
    assert data["clean_content"]
    assert data["content_hash"]
    assert data["one_sentence_summary"]
    assert data["tags"]
    assert service.calls == 1

    chunks = db_session.scalars(
        select(ArticleChunk)
        .where(ArticleChunk.article_id == data["id"])
        .order_by(ArticleChunk.chunk_index)
    ).all()
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.token_count for chunk in chunks] == [20, 21]
    assert "".join(chunk.content for chunk in chunks) == data["clean_content"]
    assert all(len(chunk.embedding) == 1024 for chunk in chunks)
    assert chunks[0].embedding[0] == 0.1
    assert chunks[1].embedding[0] == 0.2


def test_embedding_failure_sets_partial_failed_and_preserves_article_data(
    client: TestClient,
    db_session: Session,
) -> None:
    service = ErrorEmbeddingStub(EmbeddingTimeoutError("Embedding 请求超时"))
    app.dependency_overrides[get_embedding_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    data = response.json()["data"]
    assert response.status_code == 201
    assert data["embedding_status"] == "failed"
    assert data["embedding_error"] == "Embedding 请求超时"
    assert data["status"] == "partial_failed"
    assert data["fetch_status"] == "completed"
    assert data["ai_status"] == "completed"
    assert data["clean_content"]
    assert data["content_hash"]
    assert data["one_sentence_summary"]
    assert data["key_points"]
    assert data["detailed_summary"]
    assert set(data["tags"]) == {"测试", "AI"}
    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == data["id"]
        )
    ) == 0


def test_ai_failure_does_not_call_embedding(client: TestClient) -> None:
    class FailedAI:
        def generate_article_result(self, _clean_content: str):
            raise LLMResponseError("LLM 返回的结构化结果无效")

    embedding = MultiChunkEmbeddingStub()
    app.dependency_overrides[get_ai_service] = FailedAI
    app.dependency_overrides[get_embedding_service] = lambda: embedding

    response = client.post("/api/v1/articles", json=create_payload())

    data = response.json()["data"]
    assert data["ai_status"] == "failed"
    assert data["embedding_status"] == "pending"
    assert embedding.calls == 0


def test_missing_embedding_configuration_sets_safe_failure(client: TestClient) -> None:
    service = EmbeddingService(
        chunker=TokenChunker(chunk_size=400, overlap=80),
        client=OpenAICompatibleEmbeddingClient(
            base_url="",
            api_key=SecretStr(""),
            model="",
            dimension=1024,
            timeout_seconds=1,
        ),
        batch_size=10,
    )
    app.dependency_overrides[get_embedding_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    data = response.json()["data"]
    assert data["embedding_status"] == "failed"
    assert "EMBEDDING_BASE_URL" in data["embedding_error"]
    assert "EMBEDDING_API_KEY" in data["embedding_error"]
    assert "EMBEDDING_MODEL" in data["embedding_error"]


def test_failed_regeneration_preserves_existing_chunks(
    db_session: Session,
) -> None:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://embedding-regeneration.example/{uuid4()}",
        clean_content="重新生成向量时必须保留旧数据。" * 30,
        content_hash="b" * 64,
        one_sentence_summary="重新生成安全性。",
        key_points=["失败时保留旧切片"],
        detailed_summary="只有新向量全部成功后才替换旧向量。",
        status="completed",
        fetch_status="completed",
        ai_status="completed",
        embedding_status="completed",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    old_chunk = ArticleChunk(
        article_id=article.id,
        chunk_index=0,
        content="旧切片",
        token_count=3,
        embedding=[0.5] * 1024,
        chunk_metadata={"version": "old"},
    )
    db_session.add(old_chunk)
    db_session.commit()

    ArticleService.process_embedding_if_ready(
        db_session,
        article,
        ErrorEmbeddingStub(EmbeddingResponseError("Embedding 返回数量与输入不一致")),
    )

    chunks = db_session.scalars(
        select(ArticleChunk).where(ArticleChunk.article_id == article.id)
    ).all()
    assert article.embedding_status == "failed"
    assert article.status == "partial_failed"
    assert len(chunks) == 1
    assert chunks[0].content == "旧切片"
    assert chunks[0].embedding[0] == 0.5


def test_successful_regeneration_atomically_replaces_existing_chunks(
    db_session: Session,
) -> None:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://embedding-replace.example/{uuid4()}",
        clean_content="成功后原子替换旧切片。" * 30,
        content_hash="c" * 64,
        one_sentence_summary="安全替换。",
        key_points=["不产生重复 chunk_index"],
        detailed_summary="新结果完整后替换旧结果。",
        status="completed",
        fetch_status="completed",
        ai_status="completed",
        embedding_status="completed",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    db_session.add(
        ArticleChunk(
            article_id=article.id,
            chunk_index=0,
            content="旧切片",
            token_count=3,
            embedding=[0.5] * 1024,
        )
    )
    db_session.commit()

    ArticleService.process_embedding_if_ready(
        db_session,
        article,
        MultiChunkEmbeddingStub(),
    )

    chunks = db_session.scalars(
        select(ArticleChunk)
        .where(ArticleChunk.article_id == article.id)
        .order_by(ArticleChunk.chunk_index)
    ).all()
    assert article.embedding_status == "completed"
    assert article.status == "completed"
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert all(chunk.content != "旧切片" for chunk in chunks)
    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == article.id
        )
    ) == 2
