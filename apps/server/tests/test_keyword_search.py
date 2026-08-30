from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_ai_service, get_embedding_service
from app.main import app
from app.models.article import Article
from app.models.article_chunk import ArticleChunk
from app.models.article_tag import ArticleTag
from app.models.tag import Tag


def unique_keyword(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def create_search_article(
    session: Session,
    *,
    user_id: int = 1,
    title: str | None = None,
    clean_content: str | None = None,
    one_sentence_summary: str | None = None,
    detailed_summary: str | None = None,
    source_type: str = "web",
    source_name: str | None = "测试来源",
    favorite: bool = False,
    status: str = "completed",
    created_at: datetime | None = None,
) -> Article:
    article = Article(
        user_id=user_id,
        source_type=source_type,
        source_url=f"https://keyword-search.example/{uuid4()}",
        source_name=source_name,
        title=title,
        clean_content=clean_content,
        content_hash="a" * 64 if clean_content else None,
        one_sentence_summary=one_sentence_summary,
        detailed_summary=detailed_summary,
        key_points=["测试观点"] if one_sentence_summary or detailed_summary else None,
        favorite=favorite,
        status=status,
        fetch_status="completed",
        ai_status="completed",
        embedding_status="completed",
    )
    if created_at is not None:
        article.created_at = created_at
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


@pytest.mark.parametrize(
    ("field_name", "prefix"),
    [
        ("title", "标题命中"),
        ("clean_content", "正文命中"),
        ("one_sentence_summary", "一句话命中"),
        ("detailed_summary", "详细摘要命中"),
    ],
)
def test_keyword_search_matches_each_required_field(
    client: TestClient,
    db_session: Session,
    field_name: str,
    prefix: str,
) -> None:
    keyword = unique_keyword(prefix)
    values = {field_name: f"这里包含 {keyword} 关键词"}
    article = create_search_article(db_session, **values)

    response = client.get("/api/v1/search/keyword", params={"q": keyword})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["article_id"] for item in data["items"]] == [article.id]
    assert "clean_content" not in data["items"][0]
    assert "detailed_summary" not in data["items"][0]


def test_keyword_search_supports_chinese_and_trims_query(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("人工智能治理")
    article = create_search_article(
        db_session,
        title=f"关于{keyword}的实践",
    )

    response = client.get(
        "/api/v1/search/keyword",
        params={"q": f"  {keyword}  "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["article_id"] == article.id


def test_keyword_search_is_case_insensitive_for_english(
    client: TestClient,
    db_session: Session,
) -> None:
    marker = uuid4().hex
    article = create_search_article(
        db_session,
        title=f"OpenAICompatible-{marker}",
    )

    response = client.get(
        "/api/v1/search/keyword",
        params={"q": f"openaicompatible-{marker}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["article_id"] == article.id


def test_multiple_field_matches_return_article_only_once(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("多字段")
    article = create_search_article(
        db_session,
        title=keyword,
        clean_content=keyword,
        one_sentence_summary=keyword,
        detailed_summary=keyword,
    )

    response = client.get("/api/v1/search/keyword", params={"q": keyword})

    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["article_id"] for item in data["items"]] == [article.id]


@pytest.mark.parametrize("query", ["", "   "])
def test_keyword_search_rejects_empty_query(client: TestClient, query: str) -> None:
    response = client.get("/api/v1/search/keyword", params={"q": query})

    assert response.status_code == 422
    assert response.json()["code"] == 42200


def test_like_special_characters_are_matched_as_literals(
    client: TestClient,
    db_session: Session,
) -> None:
    marker = uuid4().hex
    literal_keyword = f"{marker}%_路径\\结尾"
    literal = create_search_article(db_session, title=literal_keyword)
    wildcard_decoy = create_search_article(
        db_session,
        title=f"{marker}XY路径Z结尾",
    )

    response = client.get(
        "/api/v1/search/keyword",
        params={"q": literal_keyword},
    )

    ids = [item["article_id"] for item in response.json()["data"]["items"]]
    assert literal.id in ids
    assert wildcard_decoy.id not in ids


def test_keyword_search_isolates_current_user(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("用户隔离")
    current_user_article = create_search_article(
        db_session,
        user_id=1,
        title=keyword,
    )
    other_user_article = create_search_article(
        db_session,
        user_id=2,
        title=keyword,
    )

    response = client.get("/api/v1/search/keyword", params={"q": keyword})

    ids = [item["article_id"] for item in response.json()["data"]["items"]]
    assert ids == [current_user_article.id]
    assert other_user_article.id not in ids


def test_title_priority_pagination_and_stable_order(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("排序分页")
    same_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
    older_title = create_search_article(
        db_session,
        title=f"{keyword} 旧标题",
        created_at=same_time,
    )
    newer_title = create_search_article(
        db_session,
        title=f"{keyword} 新标题",
        created_at=same_time,
    )
    newest_body = create_search_article(
        db_session,
        title="正文命中但标题不命中",
        clean_content=keyword,
        created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    first_page = client.get(
        "/api/v1/search/keyword",
        params={"q": keyword, "page": 1, "page_size": 2},
    ).json()["data"]
    second_page = client.get(
        "/api/v1/search/keyword",
        params={"q": keyword, "page": 2, "page_size": 2},
    ).json()["data"]

    assert first_page["total"] == 3
    assert [item["article_id"] for item in first_page["items"]] == [
        newer_title.id,
        older_title.id,
    ]
    assert [item["article_id"] for item in second_page["items"]] == [
        newest_body.id
    ]


def test_search_result_contains_tags_but_not_full_content(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("轻量结果")
    secret_content = f"{keyword} " + "不应出现在搜索响应中的完整正文。" * 100
    article = create_search_article(
        db_session,
        clean_content=secret_content,
        one_sentence_summary="轻量摘要",
    )
    tag = Tag(user_id=1, name=unique_keyword("搜索标签"))
    db_session.add(tag)
    db_session.flush()
    db_session.add(ArticleTag(article_id=article.id, tag_id=tag.id))
    db_session.commit()
    db_session.expire(article, ["tags"])

    response = client.get("/api/v1/search/keyword", params={"q": keyword})

    item = response.json()["data"]["items"][0]
    assert item["tags"] == [tag.name]
    assert "clean_content" not in item
    assert secret_content not in response.text


def test_no_match_returns_empty_paginated_result(client: TestClient) -> None:
    response = client.get(
        "/api/v1/search/keyword",
        params={"q": unique_keyword("完全无匹配")},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }


def test_search_is_read_only_and_does_not_call_ai_or_embedding(
    client: TestClient,
    db_session: Session,
) -> None:
    keyword = unique_keyword("只读搜索")
    article = create_search_article(
        db_session,
        title=keyword,
        clean_content="保持不变的正文",
        status="completed",
    )
    chunk = ArticleChunk(
        article_id=article.id,
        chunk_index=0,
        content="保持不变的切片",
        token_count=5,
        embedding=[0.25] * 1024,
    )
    db_session.add(chunk)
    db_session.commit()

    def forbidden_dependency():
        raise AssertionError("关键词搜索不得调用 AI 或 Embedding")

    app.dependency_overrides[get_ai_service] = forbidden_dependency
    app.dependency_overrides[get_embedding_service] = forbidden_dependency
    response = client.get("/api/v1/search/keyword", params={"q": keyword})

    assert response.status_code == 200
    persisted = db_session.get(Article, article.id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.clean_content == "保持不变的正文"
    assert db_session.scalar(
        select(func.count()).select_from(ArticleChunk).where(
            ArticleChunk.article_id == article.id
        )
    ) == 1
