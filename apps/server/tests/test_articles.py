from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.article_chunk import ArticleChunk
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
    assert body["data"]["status"] == "processing"
    assert body["data"]["fetch_status"] == "completed"
    assert body["data"]["ai_status"] == "pending"
    assert body["data"]["embedding_status"] == "pending"


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


def test_status_and_status_404(client: TestClient) -> None:
    article = create_article(client)

    response = client.get(f"/api/v1/articles/{article['id']}/status")
    missing = client.get("/api/v1/articles/9223372036854775807/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": article["id"],
        "status": "processing",
        "fetch_status": "completed",
        "ai_status": "pending",
        "embedding_status": "pending",
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
    db_session.add(
        ArticleChunk(article_id=article_id, chunk_index=0, content="级联删除验证")
    )
    db_session.commit()

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
