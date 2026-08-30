from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import OpenAICompatibleClient
from app.ai.errors import (
    AIError,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
)
from app.ai.schemas import AIArticleResult
from app.ai.service import AIService
from app.api.deps import get_ai_service, get_crawler_service
from app.crawler.errors import CrawlerFallbackError
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.services.article import ArticleService
from app.main import app


def create_payload() -> dict[str, str]:
    return {
        "source_url": f"https://ai-pipeline.example/{uuid4()}",
        "source_type": "web",
    }


class ResultAIStub:
    def __init__(self, result: AIArticleResult) -> None:
        self.result = result
        self.calls = 0

    def generate_article_result(self, _content: str) -> AIArticleResult:
        self.calls += 1
        return self.result


class ErrorAIStub:
    def __init__(self, error: AIError) -> None:
        self.error = error
        self.calls = 0

    def generate_article_result(self, _content: str) -> AIArticleResult:
        self.calls += 1
        raise self.error


def ai_result(*, tags: list[str] | None = None) -> AIArticleResult:
    return AIArticleResult(
        one_sentence_summary="文章解释了安全的结构化摘要流程。",
        key_points=["正文是唯一事实来源", "模型结果必须经过 Schema 校验"],
        detailed_summary="文章介绍了如何调用模型、校验结果并安全地持久化摘要和标签。",
        tags=tags or ["AI", "内容处理"],
    )


def test_ai_success_persists_summaries_key_points_and_tags(
    client: TestClient,
    db_session: Session,
) -> None:
    service = ResultAIStub(ai_result(tags=["AI", "摘要", "AI"]))
    app.dependency_overrides[get_ai_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["one_sentence_summary"] == "文章解释了安全的结构化摘要流程。"
    assert data["key_points"] == ["正文是唯一事实来源", "模型结果必须经过 Schema 校验"]
    assert data["detailed_summary"]
    assert set(data["tags"]) == {"AI", "摘要"}
    assert data["ai_status"] == "completed"
    assert data["ai_error"] is None
    assert data["status"] == "completed"
    assert data["fetch_status"] == "completed"
    assert data["embedding_status"] == "completed"

    persisted = db_session.scalar(select(Article).where(Article.id == data["id"]))
    assert persisted is not None
    assert persisted.one_sentence_summary == data["one_sentence_summary"]
    assert persisted.key_points == data["key_points"]
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == data["id"]
        )
    ) == 2


def test_same_user_reuses_existing_tag_without_duplicate(
    client: TestClient,
    db_session: Session,
) -> None:
    first = client.post("/api/v1/articles", json=create_payload())
    second = client.post("/api/v1/articles", json=create_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert db_session.scalar(
        select(func.count()).select_from(Tag).where(
            Tag.user_id == 1,
            Tag.name == "测试",
        )
    ) == 1
    tag_id = db_session.scalar(
        select(Tag.id).where(Tag.user_id == 1, Tag.name == "测试")
    )
    assert tag_id is not None
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.tag_id == tag_id
        )
    ) == 2


def test_ai_rerun_replaces_article_tags_only_after_success(db_session: Session) -> None:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://ai-rerun.example/{uuid4()}",
        clean_content="有效正文。" * 60,
        content_hash="a" * 64,
        status="processing",
        fetch_status="completed",
        ai_status="pending",
        embedding_status="pending",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    ArticleService.process_ai_if_ready(
        db_session,
        article,
        ResultAIStub(ai_result(tags=["保留标签", "旧标签"])),
    )
    ArticleService.process_ai_if_ready(
        db_session,
        article,
        ResultAIStub(ai_result(tags=["保留标签", "新标签"])),
    )

    current_names = set(
        db_session.scalars(
            select(Tag.name)
            .join(ArticleTag, ArticleTag.tag_id == Tag.id)
            .where(ArticleTag.article_id == article.id)
        ).all()
    )
    assert current_names == {"保留标签", "新标签"}
    assert db_session.scalar(
        select(func.count()).select_from(Tag).where(Tag.name == "旧标签")
    ) == 1


@pytest.mark.parametrize(
    "ai_error",
    [
        LLMTimeoutError("LLM 请求超时"),
        LLMAuthenticationError("LLM 鉴权失败，请检查本机配置"),
        LLMRateLimitError("LLM 服务请求过于频繁，请稍后重试"),
        LLMServiceError("LLM 服务暂时不可用"),
        LLMResponseError("LLM 返回的结构化结果无效"),
    ],
)
def test_ai_failure_preserves_content_and_sets_safe_status(
    client: TestClient,
    db_session: Session,
    ai_error: AIError,
) -> None:
    service = ErrorAIStub(ai_error)
    app.dependency_overrides[get_ai_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["fetch_status"] == "completed"
    assert data["clean_content"]
    assert data["content_hash"]
    assert data["ai_status"] == "failed"
    assert data["ai_error"] == str(ai_error)
    assert data["status"] == "partial_failed"
    assert data["embedding_status"] == "pending"
    assert data["one_sentence_summary"] is None
    assert data["tags"] == []

    persisted = db_session.scalar(select(Article).where(Article.id == data["id"]))
    assert persisted is not None
    assert persisted.clean_content == data["clean_content"]
    assert persisted.content_hash == data["content_hash"]


def test_invalid_model_json_marks_ai_failed_without_partial_data(
    client: TestClient,
) -> None:
    class InvalidRawClient:
        def complete(self, _system_prompt: str, _user_prompt: str) -> str:
            return '{"one_sentence_summary":"只有一个字段"}'

    app.dependency_overrides[get_ai_service] = lambda: AIService(InvalidRawClient())

    response = client.post("/api/v1/articles", json=create_payload())

    data = response.json()["data"]
    assert data["ai_status"] == "failed"
    assert data["ai_error"] == "LLM 返回的结构化结果无效"
    assert data["one_sentence_summary"] is None
    assert data["key_points"] is None
    assert data["detailed_summary"] is None
    assert data["tags"] == []


def test_missing_llm_configuration_marks_ai_failed(client: TestClient) -> None:
    service = AIService(
        OpenAICompatibleClient(
            base_url="",
            api_key=SecretStr(""),
            model="",
            timeout_seconds=1,
        )
    )
    app.dependency_overrides[get_ai_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ai_status"] == "failed"
    assert "LLM_BASE_URL" in data["ai_error"]
    assert "LLM_API_KEY" in data["ai_error"]
    assert "LLM_MODEL" in data["ai_error"]


def test_fetch_failure_does_not_call_ai(client: TestClient) -> None:
    class FailedCrawler:
        def fetch_article(self, _url: str) -> None:
            raise CrawlerFallbackError("HTTP 与 Playwright 均失败")

    service = ResultAIStub(ai_result())
    app.dependency_overrides[get_crawler_service] = FailedCrawler
    app.dependency_overrides[get_ai_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["fetch_status"] == "failed"
    assert data["ai_status"] == "pending"
    assert service.calls == 0
