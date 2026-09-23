from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import AIArticleResult
from app.api.deps import get_ai_service
from app.main import app
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def create_article(session: Session) -> Article:
    article = Article(
        user_id=1,
        source_type="web",
        source_url=f"https://tag-test.example/{uuid4()}",
        title="标签级联测试文章",
        clean_content="用于验证删除标签不会删除文章的正文。" * 20,
        content_hash="a" * 64,
        one_sentence_summary="标签删除不应影响文章。",
        status="processing",
        fetch_status="completed",
        ai_status="completed",
        embedding_status="pending",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


def test_create_and_list_tags_with_trim_and_stable_sort(client: TestClient) -> None:
    first_name = unique_name("乙标签")
    second_name = unique_name("甲标签")

    first = client.post("/api/v1/tags", json={"name": f"  {first_name}  "})
    second = client.post("/api/v1/tags", json={"name": second_name})
    response = client.get("/api/v1/tags")

    assert first.status_code == 201
    assert first.json()["data"]["name"] == first_name
    assert second.status_code == 201
    assert response.status_code == 200
    names = [tag["name"] for tag in response.json()["data"]]
    assert first_name in names
    assert second_name in names
    assert names == sorted(names)


def test_duplicate_tag_returns_409_without_duplicate_data(
    client: TestClient,
    db_session: Session,
) -> None:
    name = unique_name("重复标签")
    created = client.post("/api/v1/tags", json={"name": name})
    duplicate = client.post("/api/v1/tags", json={"name": f" {name} "})

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "code": 40902,
        "message": "Tag 已存在",
        "data": {"tag_id": created.json()["data"]["id"]},
    }
    assert db_session.scalar(
        select(func.count()).select_from(Tag).where(
            Tag.user_id == 1,
            Tag.name == name,
        )
    ) == 1


@pytest.mark.parametrize("name", ["", "   ", "超" * 101])
def test_tag_name_validation_rejects_invalid_values(
    client: TestClient,
    name: str,
) -> None:
    response = client.post("/api/v1/tags", json={"name": name})

    assert response.status_code == 422
    assert response.json()["code"] == 42200


def test_patch_tag_trims_name_and_preserves_article_relation(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(db_session)
    created = client.post("/api/v1/tags", json={"name": unique_name("旧名称")})
    tag_id = created.json()["data"]["id"]
    db_session.add(ArticleTag(article_id=article.id, tag_id=tag_id))
    db_session.commit()
    new_name = unique_name("新名称")

    response = client.patch(
        f"/api/v1/tags/{tag_id}",
        json={"name": f"  {new_name}  "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == new_name
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article.id,
            ArticleTag.tag_id == tag_id,
        )
    ) == 1


def test_patch_tag_rejects_duplicate_name(client: TestClient) -> None:
    first = client.post("/api/v1/tags", json={"name": unique_name("标签一")})
    second = client.post("/api/v1/tags", json={"name": unique_name("标签二")})

    response = client.patch(
        f"/api/v1/tags/{second.json()['data']['id']}",
        json={"name": first.json()["data"]["name"]},
    )

    assert response.status_code == 409
    assert response.json()["data"] == {"tag_id": first.json()["data"]["id"]}


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_update_or_delete_missing_tag_returns_404(
    client: TestClient,
    method: str,
) -> None:
    if method == "patch":
        response = client.patch(
            "/api/v1/tags/9223372036854775807",
            json={"name": "不存在"},
        )
    else:
        response = client.delete("/api/v1/tags/9223372036854775807")

    assert response.status_code == 404
    assert response.json()["code"] == 40402


def test_delete_tag_cascades_relation_but_preserves_article(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(db_session)
    original_content = article.clean_content
    original_summary = article.one_sentence_summary
    created = client.post("/api/v1/tags", json={"name": unique_name("待删除")})
    tag_id = created.json()["data"]["id"]
    db_session.add(ArticleTag(article_id=article.id, tag_id=tag_id))
    db_session.commit()

    response = client.delete(f"/api/v1/tags/{tag_id}")

    assert response.status_code == 200
    assert db_session.get(Tag, tag_id) is None
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article.id,
            ArticleTag.tag_id == tag_id,
        )
    ) == 0
    persisted_article = db_session.get(Article, article.id)
    assert persisted_article is not None
    assert persisted_article.clean_content == original_content
    assert persisted_article.one_sentence_summary == original_summary


def test_ai_generated_tag_can_be_managed_through_tags_api(
    client: TestClient,
    db_session: Session,
) -> None:
    ai_name = unique_name("AI生成")

    class UniqueTagAIStub:
        def generate_article_result(self, _clean_content: str) -> AIArticleResult:
            return AIArticleResult(
                one_sentence_summary="AI 标签管理验证。",
                key_points=["自动标签与人工管理共享数据"],
                detailed_summary="AI 创建的标签应当可以通过 Tags API 修改和删除。",
                tags=[ai_name, ai_name],
            )

    app.dependency_overrides[get_ai_service] = UniqueTagAIStub
    article_response = client.post(
        "/api/v1/articles",
        json={
            "source_url": f"https://ai-tag-api.example/{uuid4()}",
            "source_type": "web",
        },
    )
    article_id = article_response.json()["data"]["id"]

    listed = client.get("/api/v1/tags")
    ai_tag = next(tag for tag in listed.json()["data"] if tag["name"] == ai_name)
    renamed = unique_name("人工改名")
    updated = client.patch(
        f"/api/v1/tags/{ai_tag['id']}",
        json={"name": renamed},
    )
    deleted = client.delete(f"/api/v1/tags/{ai_tag['id']}")

    assert article_response.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == renamed
    assert deleted.status_code == 200
    assert db_session.get(Article, article_id) is not None
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article_id
        )
    ) == 0


def test_ai_reuses_manual_tag_without_duplicate(
    client: TestClient,
    db_session: Session,
) -> None:
    name = unique_name("共享标签")
    manual = client.post("/api/v1/tags", json={"name": name})
    tag_id = manual.json()["data"]["id"]

    class ReuseTagAIStub:
        def generate_article_result(self, _clean_content: str) -> AIArticleResult:
            return AIArticleResult(
                one_sentence_summary="复用标签。",
                key_points=["同名标签不重复创建"],
                detailed_summary="人工标签和 AI 标签使用相同的 tags 表。",
                tags=[name, name],
            )

    app.dependency_overrides[get_ai_service] = ReuseTagAIStub
    article_response = client.post(
        "/api/v1/articles",
        json={
            "source_url": f"https://ai-tag-reuse.example/{uuid4()}",
            "source_type": "web",
        },
    )
    article_id = article_response.json()["data"]["id"]

    assert article_response.status_code == 201
    assert db_session.scalar(
        select(func.count()).select_from(Tag).where(
            Tag.user_id == 1,
            Tag.name == name,
        )
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article_id,
            ArticleTag.tag_id == tag_id,
        )
    ) == 1
