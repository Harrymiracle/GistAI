from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.schemas import AIArticleTopicResult
from app.api.deps import get_ai_service, get_current_user_id
from app.main import app
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.db.session import SessionLocal
from app.core.exceptions import TagStatusConflictError
from app.services.tag import TagService


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def create_article(session: Session, user_id: int = 1) -> Article:
    article = Article(
        user_id=user_id,
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


def test_create_and_list_active_tags_with_counts_and_c_sort(
    client: TestClient, db_session: Session
) -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    suffix = uuid4().hex[:8]
    names = [f"中文{suffix}", f"a{suffix}", f"@{suffix}", f"A{suffix}", f"零文章{suffix}"]
    created = [client.post("/api/v1/tags", json={"name": name}) for name in names]
    ids = [response.json()["data"]["id"] for response in created]
    assert all(response.status_code == 201 for response in created)
    assert all(response.json()["data"]["article_count"] == 0 for response in created)

    first = create_article(db_session, user_id=user_id)
    foreign = create_article(db_session, user_id=2)
    db_session.add_all(
        [
            ArticleTag(article_id=first.id, tag_id=ids[1]),
            ArticleTag(article_id=first.id, tag_id=ids[0]),
            ArticleTag(article_id=first.id, tag_id=ids[2]),
            ArticleTag(article_id=first.id, tag_id=ids[3]),
            ArticleTag(article_id=foreign.id, tag_id=ids[0]),
        ]
    )
    db_session.add(Tag(user_id=user_id, name=unique_name("待整理"), status="pending"))
    db_session.add(Tag(user_id=2, name=unique_name("其他用户"), status="active"))
    db_session.commit()

    response = client.get("/api/v1/tags")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["id"] for item in data] == [ids[2], ids[3], ids[1], ids[0], ids[4]]
    assert [item["article_count"] for item in data] == [1, 1, 1, 1, 0]


def test_tag_payload_rejects_status_and_pending_crud_conflicts(
    client: TestClient, db_session: Session
) -> None:
    pending = Tag(user_id=1, name=unique_name("待整理"), status="pending")
    foreign = Tag(user_id=2, name=unique_name("外部"), status="active")
    db_session.add_all([pending, foreign])
    db_session.commit()

    assert client.post("/api/v1/tags", json={"name": unique_name("手动"), "status": "pending"}).json()["code"] == 42200
    active = client.post("/api/v1/tags", json={"name": unique_name("正式")})
    assert active.status_code == 201
    assert active.json()["data"]["article_count"] == 0
    assert db_session.get(Tag, active.json()["data"]["id"]).status == "active"
    assert client.patch(f"/api/v1/tags/{active.json()['data']['id']}", json={"name": "改名", "status": "pending"}).json()["code"] == 42200

    for method in ("patch", "delete"):
        response = (
            client.patch(f"/api/v1/tags/{pending.id}", json={"name": unique_name("修改")})
            if method == "patch"
            else client.delete(f"/api/v1/tags/{pending.id}")
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40905
        foreign_response = (
            client.patch(f"/api/v1/tags/{foreign.id}", json={"name": unique_name("修改")})
            if method == "patch"
            else client.delete(f"/api/v1/tags/{foreign.id}")
        )
        assert foreign_response.status_code == 404
        assert foreign_response.json()["code"] == 40402


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


def test_ai_suggested_topic_can_be_promoted_and_managed_through_tags_api(
    client: TestClient,
    db_session: Session,
) -> None:
    ai_name = unique_name("AI生成")

    class UniqueTagAIStub:
        def generate_article_summary_with_topics(
            self,
            _clean_content: str,
            _active_topic_names: list[str],
        ) -> AIArticleTopicResult:
            return AIArticleTopicResult(
                one_sentence_summary="AI 标签管理验证。",
                key_points=["自动标签与人工管理共享数据"],
                detailed_summary="AI 创建的标签应当可以通过 Tags API 修改和删除。",
                topics=[],
                suggested_topic=ai_name,
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

    pending = client.get("/api/v1/tags/pending").json()["data"]
    ai_tag = next(tag for tag in pending if tag["name"] == ai_name)
    promoted = client.post(f"/api/v1/tags/{ai_tag['id']}/promote")
    renamed = unique_name("人工改名")
    updated = client.patch(
        f"/api/v1/tags/{ai_tag['id']}",
        json={"name": renamed},
    )
    deleted = client.delete(f"/api/v1/tags/{ai_tag['id']}")

    assert article_response.status_code == 201
    assert promoted.status_code == 200
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
        def generate_article_summary_with_topics(
            self,
            _clean_content: str,
            _active_topic_names: list[str],
        ) -> AIArticleTopicResult:
            return AIArticleTopicResult(
                one_sentence_summary="复用标签。",
                key_points=["同名标签不重复创建"],
                detailed_summary="人工标签和 AI 标签使用相同的 tags 表。",
                topics=[name, name],
                suggested_topic=None,
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


def test_pending_list_sources_order_and_owner(client: TestClient, db_session: Session) -> None:
    old = Tag(user_id=1, name=unique_name("旧建议"), status="pending")
    new = Tag(user_id=1, name=unique_name("新建议"), status="pending")
    foreign = Tag(user_id=2, name=unique_name("外部建议"), status="pending")
    db_session.add_all([old, new, foreign])
    db_session.flush()
    first = create_article(db_session)
    first.title = None
    second = create_article(db_session)
    outsider = create_article(db_session, user_id=2)
    db_session.add_all([
        ArticleTag(article_id=second.id, tag_id=old.id),
        ArticleTag(article_id=first.id, tag_id=old.id),
        ArticleTag(article_id=outsider.id, tag_id=old.id),
        ArticleTag(article_id=outsider.id, tag_id=foreign.id),
    ])
    db_session.commit()

    response = client.get("/api/v1/tags/pending")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [new.id, old.id]
    assert response.json()["data"][1]["sources"] == [
        {"article_id": first.id, "title": None},
        {"article_id": second.id, "title": second.title},
    ]


def test_promote_preserves_links_and_rejects_repeat(client: TestClient, db_session: Session) -> None:
    pending = Tag(user_id=1, name=unique_name("提升"), status="pending")
    db_session.add(pending)
    db_session.flush()
    article = create_article(db_session)
    db_session.add(ArticleTag(article_id=article.id, tag_id=pending.id))
    db_session.commit()

    promoted = client.post(f"/api/v1/tags/{pending.id}/promote")
    repeated = client.post(f"/api/v1/tags/{pending.id}/promote")

    assert promoted.status_code == 200
    assert promoted.json()["data"]["article_count"] == 1
    assert db_session.get(Tag, pending.id).status == "active"
    assert db_session.get(ArticleTag, (article.id, pending.id)) is not None
    assert repeated.status_code == 409
    assert repeated.json()["code"] == 40905


def test_merge_deduplicates_and_deletes_pending(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = Tag(user_id=1, name=unique_name("合并来源"), status="pending")
    target = Tag(user_id=1, name=unique_name("合并目标"), status="active")
    db_session.add_all([pending, target])
    db_session.flush()
    first = create_article(db_session)
    second = create_article(db_session)
    db_session.add_all([
        ArticleTag(article_id=first.id, tag_id=pending.id),
        ArticleTag(article_id=second.id, tag_id=pending.id),
        ArticleTag(article_id=first.id, tag_id=target.id),
    ])
    db_session.commit()
    commit_count = 0
    original_commit = db_session.commit

    def count_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        original_commit()

    monkeypatch.setattr(db_session, "commit", count_commit)

    response = client.post(f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": target.id})

    assert response.status_code == 200
    assert commit_count == 1
    assert response.json()["data"] == {
        "tag_id": pending.id,
        "target_tag_id": target.id,
        "affected_article_count": 2,
    }
    assert db_session.get(Tag, pending.id) is None
    assert db_session.get(Article, first.id) is not None
    assert db_session.get(Article, second.id) is not None
    assert db_session.scalar(select(func.count()).select_from(ArticleTag).where(ArticleTag.tag_id == target.id)) == 2
    assert client.post(f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": target.id}).status_code == 404


def test_merge_article_set_retry_exhaustion_returns_409_without_changes(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = Tag(user_id=1, name=unique_name("重试耗尽来源"), status="pending")
    target = Tag(user_id=1, name=unique_name("重试耗尽目标"), status="active")
    db_session.add_all([pending, target])
    db_session.flush()
    first = create_article(db_session)
    second = create_article(db_session)
    db_session.add(ArticleTag(article_id=first.id, tag_id=pending.id))
    db_session.commit()
    pending_id = pending.id
    target_id = target.id
    first_id = first.id
    second_id = second.id
    query_count = 0
    rollback_count = 0
    commit_count = 0
    original_rollback = db_session.rollback
    original_commit = db_session.commit

    def changing_article_ids(
        _session: Session,
        _tag_id: int,
        _user_id: int,
    ) -> tuple[int, ...]:
        nonlocal query_count
        query_count += 1
        if query_count % 2:
            return (first_id,)
        return (first_id, second_id)

    def count_rollback() -> None:
        nonlocal rollback_count
        rollback_count += 1
        original_rollback()

    def count_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        original_commit()

    monkeypatch.setattr(
        TagService,
        "_list_merge_article_ids",
        staticmethod(changing_article_ids),
        raising=False,
    )
    monkeypatch.setattr(db_session, "rollback", count_rollback)
    monkeypatch.setattr(db_session, "commit", count_commit)

    response = client.post(
        f"/api/v1/tags/{pending_id}/merge",
        json={"target_tag_id": target_id},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": 40907,
        "message": "待整理主题关联正在变化，请稍后重试",
        "data": None,
    }
    assert query_count == 6
    assert rollback_count == 3
    assert commit_count == 0
    db_session.expire_all()
    assert db_session.get(Tag, pending_id).status == "pending"
    assert db_session.get(Tag, target_id).status == "active"
    assert db_session.get(ArticleTag, (first_id, pending_id)) is not None
    assert db_session.get(ArticleTag, (second_id, pending_id)) is None
    assert db_session.get(ArticleTag, (first_id, target_id)) is None
    assert db_session.get(ArticleTag, (second_id, target_id)) is None


def test_ignore_deletes_links_only(client: TestClient, db_session: Session) -> None:
    pending = Tag(user_id=1, name=unique_name("忽略"), status="pending")
    db_session.add(pending)
    db_session.flush()
    article = create_article(db_session)
    db_session.add(ArticleTag(article_id=article.id, tag_id=pending.id))
    db_session.commit()

    response = client.post(f"/api/v1/tags/{pending.id}/ignore")

    assert response.status_code == 200
    assert response.json()["data"] == {"tag_id": pending.id, "affected_article_count": 1}
    assert db_session.get(Tag, pending.id) is None
    assert db_session.get(Article, article.id) is not None
    assert db_session.get(ArticleTag, (article.id, pending.id)) is None
    assert client.post(f"/api/v1/tags/{pending.id}/ignore").status_code == 404


def test_pending_actions_reject_cross_user_and_wrong_status(
    client: TestClient, db_session: Session
) -> None:
    pending = Tag(user_id=1, name=unique_name("建议"), status="pending")
    active = Tag(user_id=1, name=unique_name("正式"), status="active")
    foreign = Tag(user_id=2, name=unique_name("外部"), status="pending")
    db_session.add_all([pending, active, foreign])
    db_session.commit()

    assert client.post(f"/api/v1/tags/{foreign.id}/promote").status_code == 404
    assert client.post(f"/api/v1/tags/{active.id}/promote").json()["code"] == 40905
    assert client.post(f"/api/v1/tags/{active.id}/ignore").json()["code"] == 40905
    assert client.post(f"/api/v1/tags/{active.id}/merge", json={"target_tag_id": active.id}).json()["code"] == 40905
    assert client.post(f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": pending.id}).json()["code"] == 40905
    assert client.post(f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": foreign.id}).status_code == 404


def test_pending_action_failure_rolls_back(client: TestClient, db_session: Session, monkeypatch) -> None:
    pending = Tag(user_id=1, name=unique_name("回滚来源"), status="pending")
    target = Tag(user_id=1, name=unique_name("回滚目标"), status="active")
    db_session.add_all([pending, target])
    db_session.flush()
    article = create_article(db_session)
    db_session.add(ArticleTag(article_id=article.id, tag_id=pending.id))
    db_session.commit()

    def fail_after_insert(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("注入合并失败")

    monkeypatch.setattr(db_session, "delete", fail_after_insert)
    with pytest.raises(RuntimeError, match="注入合并失败"):
        client.post(f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": target.id})

    db_session.expire_all()
    assert db_session.get(Tag, pending.id) is not None
    assert db_session.get(ArticleTag, (article.id, pending.id)) is not None
    assert db_session.get(ArticleTag, (article.id, target.id)) is None


def test_promote_same_name_conflict_rolls_back(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    pending = Tag(user_id=1, name=unique_name("并发冲突"), status="pending")
    db_session.add(pending)
    db_session.commit()

    def fail_commit() -> None:
        raise IntegrityError("并发唯一约束冲突", {}, None)

    monkeypatch.setattr(db_session, "commit", fail_commit)
    response = client.post(f"/api/v1/tags/{pending.id}/promote")

    assert response.status_code == 409
    assert response.json()["code"] == 40905
    db_session.expire_all()
    assert db_session.get(Tag, pending.id).status == "pending"


def test_concurrent_pending_action_returns_conflict() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        pending = Tag(user_id=user_id, name=unique_name("并发建议"), status="pending")
        setup.add(pending)
        setup.commit()
        tag_id = pending.id

    backend_pids: Queue[int] = Queue(maxsize=1)

    def promote_in_second_session() -> tuple[int, str]:
        with SessionLocal() as second:
            backend_pid = second.scalar(text("SELECT pg_backend_pid()"))
            backend_pids.put(backend_pid)
            try:
                TagService.promote_pending(second, tag_id, user_id)
            except TagStatusConflictError:
                return backend_pid, "conflict"
            return backend_pid, "unexpected-success"

    try:
        with SessionLocal() as first, ThreadPoolExecutor(max_workers=1) as pool:
            locked = first.scalar(select(Tag).where(Tag.id == tag_id).with_for_update())
            assert locked is not None
            locked.status = "active"
            first.flush()
            future = pool.submit(promote_in_second_session)
            try:
                second_pid = backend_pids.get(timeout=5)
                deadline = monotonic() + 5
                blocked = False
                while monotonic() < deadline:
                    with SessionLocal() as observer:
                        blocked = bool(
                            observer.scalar(
                                text(
                                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                    "WHERE pid = :pid AND datname = current_database() "
                                    "AND wait_event_type = 'Lock' AND query LIKE '%tags%FOR UPDATE%')"
                                ),
                                {"pid": second_pid},
                            )
                        )
                    if blocked:
                        break
                    sleep(0.02)
                assert blocked, "第二个会话未等待标签行锁"
                first.commit()
                assert future.result(timeout=5)[1] == "conflict"
            finally:
                first.rollback()
    finally:
        with SessionLocal() as cleanup:
            tag = cleanup.get(Tag, tag_id)
            if tag is not None:
                cleanup.delete(tag)
                cleanup.commit()


def test_delete_active_tag_rejects_cross_user_association(
    client: TestClient, db_session: Session
) -> None:
    tag = Tag(user_id=1, name=unique_name("异常正式关联"), status="active")
    db_session.add(tag)
    db_session.flush()
    own_article = create_article(db_session)
    foreign_article = create_article(db_session, user_id=2)
    db_session.add_all([
        ArticleTag(article_id=own_article.id, tag_id=tag.id),
        ArticleTag(article_id=foreign_article.id, tag_id=tag.id),
    ])
    db_session.commit()

    response = client.delete(f"/api/v1/tags/{tag.id}")

    assert response.status_code == 409
    assert response.json()["code"] == 40906
    assert response.json()["data"] is None
    db_session.expire_all()
    assert db_session.get(Tag, tag.id).status == "active"
    for article in (own_article, foreign_article):
        assert db_session.get(Article, article.id) is not None
        assert db_session.get(ArticleTag, (article.id, tag.id)) is not None


def test_merge_pending_rejects_cross_user_association_without_partial_links(
    client: TestClient, db_session: Session
) -> None:
    pending = Tag(user_id=1, name=unique_name("异常归入来源"), status="pending")
    target = Tag(user_id=1, name=unique_name("异常归入目标"), status="active")
    db_session.add_all([pending, target])
    db_session.flush()
    own_article = create_article(db_session)
    foreign_article = create_article(db_session, user_id=2)
    db_session.add_all([
        ArticleTag(article_id=own_article.id, tag_id=pending.id),
        ArticleTag(article_id=foreign_article.id, tag_id=pending.id),
    ])
    db_session.commit()

    response = client.post(
        f"/api/v1/tags/{pending.id}/merge", json={"target_tag_id": target.id}
    )

    assert response.status_code == 409
    assert response.json()["code"] == 40906
    assert response.json()["data"] is None
    db_session.expire_all()
    assert db_session.get(Tag, pending.id).status == "pending"
    assert db_session.get(Tag, target.id).status == "active"
    for article in (own_article, foreign_article):
        assert db_session.get(Article, article.id) is not None
        assert db_session.get(ArticleTag, (article.id, pending.id)) is not None
        assert db_session.get(ArticleTag, (article.id, target.id)) is None


def test_ignore_pending_rejects_cross_user_association(
    client: TestClient, db_session: Session
) -> None:
    pending = Tag(user_id=1, name=unique_name("异常忽略来源"), status="pending")
    db_session.add(pending)
    db_session.flush()
    own_article = create_article(db_session)
    foreign_article = create_article(db_session, user_id=2)
    db_session.add_all([
        ArticleTag(article_id=own_article.id, tag_id=pending.id),
        ArticleTag(article_id=foreign_article.id, tag_id=pending.id),
    ])
    db_session.commit()

    response = client.post(f"/api/v1/tags/{pending.id}/ignore")

    assert response.status_code == 409
    assert response.json()["code"] == 40906
    assert response.json()["data"] is None
    db_session.expire_all()
    assert db_session.get(Tag, pending.id).status == "pending"
    for article in (own_article, foreign_article):
        assert db_session.get(Article, article.id) is not None
        assert db_session.get(ArticleTag, (article.id, pending.id)) is not None
