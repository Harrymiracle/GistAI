from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
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
from app.ai.schemas import AIArticleSummaryResult, AIArticleTopicResult
from app.ai.service import AIService
from app.api.deps import get_ai_service, get_crawler_service, get_embedding_service
from app.crawler.errors import CrawlerFallbackError
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.services.article import ArticleService
from app.services.article_topic import ArticleTopicService
from app.main import app


def create_payload() -> dict[str, str]:
    return {
        "source_url": f"https://ai-pipeline.example/{uuid4()}",
        "source_type": "web",
    }


class ResultAIStub:
    def __init__(self, result: AIArticleTopicResult) -> None:
        self.result = result
        self.calls = 0
        self.active_topic_names: list[list[str]] = []

    def generate_article_summary_with_topics(
        self,
        _content: str,
        active_topic_names: list[str],
    ) -> AIArticleTopicResult:
        self.calls += 1
        self.active_topic_names.append(active_topic_names)
        return self.result


class ErrorAIStub:
    def __init__(self, error: AIError) -> None:
        self.error = error
        self.calls = 0

    def generate_article_summary_with_topics(
        self,
        _content: str,
        _active_topic_names: list[str],
    ) -> AIArticleTopicResult:
        self.calls += 1
        raise self.error


def ai_result(
    *,
    topics: list[str] | None = None,
    suggested_topic: str | None = None,
) -> AIArticleTopicResult:
    return AIArticleTopicResult(
        one_sentence_summary="文章解释了安全的结构化摘要流程。",
        key_points=["正文是唯一事实来源", "模型结果必须经过 Schema 校验"],
        detailed_summary="文章介绍了如何调用模型、校验结果并安全地持久化摘要和标签。",
        topics=topics or [],
        suggested_topic=suggested_topic,
    )


def test_initial_ai_uses_owned_active_catalog_and_does_not_create_arbitrary_active(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            Tag(user_id=1, name="AI", status="active"),
            Tag(user_id=1, name="摘要", status="active"),
            Tag(user_id=2, name="外部主题", status="active"),
        ]
    )
    db_session.commit()
    service = ResultAIStub(
        ai_result(topics=["AI", "任意新标签", "摘要"], suggested_topic="内容治理")
    )
    app.dependency_overrides[get_ai_service] = lambda: service

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["one_sentence_summary"] == "文章解释了安全的结构化摘要流程。"
    assert data["key_points"] == ["正文是唯一事实来源", "模型结果必须经过 Schema 校验"]
    assert data["detailed_summary"]
    assert set(data["tags"]) == {"AI", "摘要"}
    assert data["pending_topics"] == ["内容治理"]
    assert service.active_topic_names == [["AI", "摘要"]]
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
    ) == 3
    assert db_session.scalar(
        select(func.count()).select_from(Tag).where(
            Tag.user_id == 1,
            Tag.name == "任意新标签",
        )
    ) == 0


def test_new_article_uses_topic_mode_and_regenerate_uses_summary_mode(
    client: TestClient,
) -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.system_prompts: list[str] = []

        def complete(self, system_prompt: str, _user_prompt: str, **_kwargs: object) -> str:
            self.system_prompts.append(system_prompt)
            if _kwargs.get("purpose") == "article_summary_topics":
                return ai_result().model_dump_json()
            return AIArticleSummaryResult(
                one_sentence_summary="仅摘要结果",
                key_points=["只更新摘要"],
                detailed_summary="普通重新生成不会处理主题。",
            ).model_dump_json()

    recording_client = RecordingClient()
    app.dependency_overrides[get_ai_service] = lambda: AIService(recording_client)

    created = client.post("/api/v1/articles", json=create_payload())
    assert created.status_code == 201
    article_id = created.json()["data"]["id"]
    regenerated = client.post(f"/api/v1/articles/{article_id}/regenerate-ai")

    assert regenerated.status_code == 200
    assert len(recording_client.system_prompts) == 2
    assert recording_client.system_prompts[0] != recording_client.system_prompts[1]
    assert "topics" in recording_client.system_prompts[0]
    assert "topics" not in recording_client.system_prompts[1]
    assert "最核心的内容或结论" in recording_client.system_prompts[0]
    assert regenerated.json()["data"]["one_sentence_summary"] == "仅摘要结果"


def test_same_user_reuses_existing_tag_without_duplicate(
    client: TestClient,
    db_session: Session,
) -> None:
    db_session.add(Tag(user_id=1, name="测试", status="active"))
    db_session.commit()
    service = ResultAIStub(ai_result(topics=["测试"]))
    app.dependency_overrides[get_ai_service] = lambda: service
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
    db_session.add_all(
        [
            Tag(user_id=1, name="保留标签", status="active"),
            Tag(user_id=1, name="旧标签", status="active"),
            Tag(user_id=1, name="新标签", status="active"),
        ]
    )
    db_session.commit()
    db_session.refresh(article)

    ArticleService.process_ai_if_ready(
        db_session,
        article,
        1,
        ResultAIStub(ai_result(topics=["保留标签", "旧标签"])),
    )
    ArticleService.process_ai_if_ready(
        db_session,
        article,
        1,
        ResultAIStub(ai_result(topics=["保留标签", "新标签"])),
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


def test_initial_topic_save_failure_marks_ai_failed_without_partial_data(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suggestion = f"保存失败建议-{uuid4()}"
    service = ResultAIStub(ai_result(suggested_topic=suggestion))
    original_replace = ArticleTopicService.replace_article_topics

    def fail_after_replace(*args: object, **kwargs: object) -> None:
        original_replace(*args, **kwargs)
        db_session.flush()
        db_session.execute(
            text(
                "INSERT INTO tags (user_id, name, status) "
                "VALUES (1, :name, 'invalid')"
            ),
            {"name": f"约束失败-{uuid4()}"},
        )

    class EmbeddingMustNotRun:
        def generate(self, _content: str):
            raise AssertionError("主题保存失败后不应继续 Embedding")

    monkeypatch.setattr(ArticleTopicService, "replace_article_topics", fail_after_replace)
    app.dependency_overrides[get_ai_service] = lambda: service
    app.dependency_overrides[get_embedding_service] = EmbeddingMustNotRun

    response = client.post("/api/v1/articles", json=create_payload())

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ai_status"] == "failed"
    assert data["ai_error"] == "AI 结果保存失败"
    assert data["one_sentence_summary"] is None
    assert data["tags"] == []
    assert data["pending_topics"] == []
    assert db_session.scalar(select(Tag.id).where(Tag.name == suggestion)) is None


def test_topic_save_revalidates_active_status_after_model_call(
    db_session: Session,
) -> None:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://latest-topic.example/{uuid4()}",
        clean_content="保存前主题状态复核正文。" * 30,
        content_hash="b" * 64,
        status="processing",
        fetch_status="completed",
        ai_status="pending",
        embedding_status="pending",
    )
    active = Tag(user_id=1, name=f"调用后失效-{uuid4()}", status="active")
    db_session.add_all([article, active])
    db_session.commit()

    class StatusChangingAI:
        def generate_article_summary_with_topics(
            self,
            _content: str,
            active_topic_names: list[str],
        ) -> AIArticleTopicResult:
            assert active.name in active_topic_names
            active.status = "pending"
            db_session.commit()
            return ai_result(topics=[active.name])

    ArticleService.process_ai_if_ready(db_session, article, 1, StatusChangingAI())

    db_session.expire_all()
    assert db_session.get(Article, article.id).ai_status == "completed"
    assert db_session.get(Tag, active.id).status == "pending"
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article.id
        )
    ) == 0


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
        def complete(
            self,
            _system_prompt: str,
            _user_prompt: str,
            **_options: object,
        ) -> str:
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
