from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.article_chunk import ArticleChunk
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.services.article import ArticleService


def article_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_url": f"https://example.com/articles/{uuid4()}",
        "source_type": "web",
        "title": "测试文章",
    }
    payload.update(overrides)
    return payload


def create_article(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/articles", json=article_payload(**overrides))
    assert response.status_code == 201
    return response.json()["data"]


def test_create_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/articles",
        json=article_payload(source_name="示例站点", favorite=True),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 20100
    assert body["data"]["user_id"] == 1
    assert body["data"]["favorite"] is True
    assert body["data"]["status"] == "completed"
    assert body["data"]["fetch_status"] == "completed"
    assert body["data"]["ai_status"] == "completed"
    assert body["data"]["one_sentence_summary"] == "测试文章的一句话总结。"
    assert body["data"]["tags"] == []
    assert body["data"]["embedding_status"] == "completed"


def test_invalid_url_returns_unified_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/articles",
        json=article_payload(source_url="not-a-valid-url"),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 42200
    assert body["message"] == "请求参数校验失败"
    assert body["data"]["errors"]


def test_duplicate_url_returns_409_with_existing_id(client: TestClient) -> None:
    payload = article_payload()
    first = client.post("/api/v1/articles", json=payload)
    duplicate = client.post("/api/v1/articles", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["code"] == 40901
    assert body["message"] == "Article 已存在"
    assert body["data"]["article_id"] == first.json()["data"]["id"]


def test_list_is_paginated_lightweight_and_newest_first(client: TestClient) -> None:
    source_type = f"test-{uuid4().hex[:8]}"
    first = create_article(client, source_type=source_type, title="第一篇")
    second = create_article(client, source_type=source_type, title="第二篇")

    response = client.get(
        "/api/v1/articles",
        params={"source_type": source_type, "page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["items"][0]["id"] == second["id"]
    assert data["items"][0]["id"] != first["id"]
    assert "clean_content" not in data["items"][0]


def test_detail_and_detail_404(client: TestClient) -> None:
    article = create_article(client)

    response = client.get(f"/api/v1/articles/{article['id']}")
    missing = client.get("/api/v1/articles/9223372036854775807")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == article["id"]
    assert "clean_content" in response.json()["data"]
    assert missing.status_code == 404
    assert missing.json()["message"] == "Article 不存在"


def test_patch_and_patch_404(client: TestClient) -> None:
    article = create_article(client, favorite=False)

    response = client.patch(
        f"/api/v1/articles/{article['id']}",
        json={"title": "修改后的标题", "favorite": True},
    )
    missing = client.patch(
        "/api/v1/articles/9223372036854775807",
        json={"favorite": True},
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "修改后的标题"
    assert response.json()["data"]["favorite"] is True
    assert missing.status_code == 404


def test_patch_title_updates_existing_url_like_title_in_detail_and_list(client: TestClient) -> None:
    article = create_article(client, title="/articles/old-path")

    response = client.patch(
        f"/api/v1/articles/{article['id']}",
        json={"title": "  新的文章标题  "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "新的文章标题"
    detail = client.get(f"/api/v1/articles/{article['id']}").json()["data"]
    listed = client.get("/api/v1/articles").json()["data"]["items"]
    assert detail["title"] == "新的文章标题"
    assert next(item for item in listed if item["id"] == article["id"])["title"] == "新的文章标题"


def test_patch_title_rejects_blank_and_overlong_values(client: TestClient) -> None:
    article = create_article(client)

    for title in ("  ", "题" * 256):
        response = client.patch(f"/api/v1/articles/{article['id']}", json={"title": title})
        assert response.status_code == 422

    assert client.get(f"/api/v1/articles/{article['id']}").json()["data"]["title"] == "测试文章"


def test_automatic_fetch_uses_extracted_title_when_none_provided(client: TestClient) -> None:
    article = create_article(client, title=None)

    assert article["title"] == "抓取标题"


def test_status_and_status_404(client: TestClient) -> None:
    article = create_article(client)

    response = client.get(f"/api/v1/articles/{article['id']}/status")
    missing = client.get("/api/v1/articles/9223372036854775807/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": article["id"],
        "status": "completed",
        "fetch_status": "completed",
        "ai_status": "completed",
        "embedding_status": "completed",
        "fetch_error": None,
        "ai_error": None,
        "embedding_error": None,
    }
    assert missing.status_code == 404


def test_delete_cascades_relations_and_delete_404(
    client: TestClient,
    db_session: Session,
) -> None:
    article = create_article(client)
    article_id = int(article["id"])
    tag = Tag(user_id=1, name=f"test-tag-{uuid4()}")
    db_session.add(tag)
    db_session.flush()
    db_session.add(ArticleTag(article_id=article_id, tag_id=tag.id))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == article_id
        )
    ) == 1

    response = client.delete(f"/api/v1/articles/{article_id}")
    missing = client.delete(f"/api/v1/articles/{article_id}")

    assert response.status_code == 200
    assert response.json()["data"]["article_id"] == article_id
    assert missing.status_code == 404
    assert db_session.scalar(
        select(func.count()).select_from(ArticleTag).where(
            ArticleTag.article_id == article_id
        )
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == article_id
        )
    ) == 0


def test_database_error_does_not_expose_traceback(
    client: TestClient,
    monkeypatch,
) -> None:
    def raise_database_error(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(ArticleService, "list_articles", raise_database_error)
    response = client.get("/api/v1/articles")

    assert response.status_code == 500
    body_text = response.text
    assert response.json() == {
        "code": 50001,
        "message": "数据库操作失败",
        "data": None,
    }
    assert "private database detail" not in body_text
    assert "Traceback" not in body_text


def test_article_list_detail_split_active_and_pending(
    client: TestClient, db_session: Session
) -> None:
    source_type = f"split-{uuid4().hex[:8]}"
    article = create_article(client, source_type=source_type)
    active = Tag(user_id=1, name=f"正式-{uuid4()}", status="active")
    pending = Tag(user_id=1, name=f"待整理-{uuid4()}", status="pending")
    foreign = Tag(user_id=2, name=f"其他用户-{uuid4()}", status="active")
    db_session.add_all([active, pending, foreign])
    db_session.flush()
    db_session.add_all([
        ArticleTag(article_id=article["id"], tag_id=active.id),
        ArticleTag(article_id=article["id"], tag_id=pending.id),
        ArticleTag(article_id=article["id"], tag_id=foreign.id),
    ])
    db_session.commit()
    db_session.expire_all()

    detail = client.get(f"/api/v1/articles/{article['id']}").json()["data"]
    listed = client.get("/api/v1/articles", params={"source_type": source_type}).json()["data"]["items"][0]
    updated = client.patch(f"/api/v1/articles/{article['id']}", json={"favorite": True}).json()["data"]

    for result in (detail, listed, updated):
        assert active.name in result["tags"]
        assert pending.name not in result["tags"]
        assert foreign.name not in result["tags"]
        assert result["pending_topics"] == [pending.name]
    assert article["pending_topics"] == []


def test_article_filter_rejects_pending_and_other_user(client: TestClient, db_session: Session) -> None:
    pending = Tag(user_id=1, name=f"待筛选-{uuid4()}", status="pending")
    foreign = Tag(user_id=2, name=f"外部筛选-{uuid4()}", status="active")
    db_session.add_all([pending, foreign])
    db_session.commit()

    for tag_id in (pending.id, foreign.id, 9223372036854775807):
        response = client.get("/api/v1/articles", params={"tag_id": tag_id})
        assert response.status_code == 404
        assert response.json()["code"] == 40402


def test_article_filter_active_counts_only_owned_articles(
    client: TestClient, db_session: Session
) -> None:
    active = Tag(user_id=1, name=f"筛选-{uuid4()}", status="active")
    db_session.add(active)
    db_session.flush()
    owned = create_article(client)
    foreign_article = Article(
        user_id=2,
        source_type="web",
        source_url=f"https://other.example/{uuid4()}",
        title="其他用户文章",
    )
    db_session.add(foreign_article)
    db_session.flush()
    db_session.add_all([
        ArticleTag(article_id=owned["id"], tag_id=active.id),
        ArticleTag(article_id=foreign_article.id, tag_id=active.id),
    ])
    db_session.commit()

    response = client.get("/api/v1/articles", params={"tag_id": active.id})

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1
    assert [item["id"] for item in response.json()["data"]["items"]] == [owned["id"]]
