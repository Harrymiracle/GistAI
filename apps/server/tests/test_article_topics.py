from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.schemas import AIArticleTopicResult
from app.core.exceptions import ArticleNotFoundError
from app.db.session import SessionLocal, engine
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.services.article import ArticleService
from app.services.article_topic import ArticleTopicPlan, ArticleTopicService
from app.services.tag import TagService


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def make_result(
    topics: list[str] | None = None,
    suggested_topic: str | None = None,
) -> AIArticleTopicResult:
    return AIArticleTopicResult(
        one_sentence_summary="新的一句话摘要",
        key_points=["新要点一", "新要点二"],
        detailed_summary="新的详细摘要",
        topics=topics or [],
        suggested_topic=suggested_topic,
    )


def create_article(session: Session, user_id: int = 1) -> Article:
    article = Article(
        user_id=user_id,
        source_type="web",
        source_url=f"https://article-topic.example/{uuid4()}",
        title="文章主题保存测试",
        clean_content="用于文章主题保存测试的正文。" * 20,
        content_hash="a" * 64,
        one_sentence_summary="旧的一句话摘要",
        detailed_summary="旧的详细摘要",
        key_points=["旧要点"],
        status="processing",
        fetch_status="completed",
        ai_status="processing",
        embedding_status="completed",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


def add_tag(session: Session, name: str, *, user_id: int = 1, status: str = "active") -> Tag:
    tag = Tag(user_id=user_id, name=name, status=status)
    session.add(tag)
    session.flush()
    return tag


def linked_tag_ids(session: Session, article_id: int) -> list[int]:
    return list(
        session.scalars(
            select(ArticleTag.tag_id)
            .where(ArticleTag.article_id == article_id)
            .order_by(ArticleTag.tag_id)
        )
    )


def test_list_active_names_only_returns_current_user_in_c_order(db_session: Session) -> None:
    suffix = uuid4().hex[:8]
    expected = [f"@{suffix}", f"A{suffix}", f"a{suffix}", f"中文{suffix}"]
    db_session.add_all(
        [Tag(user_id=1, name=name, status="active") for name in reversed(expected)]
        + [
            Tag(user_id=1, name=f"待整理{suffix}", status="pending"),
            Tag(user_id=2, name=f"外部{suffix}", status="active"),
        ]
    )
    db_session.flush()

    assert ArticleTopicService.list_active_names(db_session, 1) == expected


@pytest.mark.parametrize(
    ("candidate_count", "expected_count"),
    [(0, 0), (1, 1), (2, 2), (3, 2)],
)
def test_resolve_for_save_caps_revalidated_active_topics_at_two(
    db_session: Session,
    candidate_count: int,
    expected_count: int,
) -> None:
    tags = [add_tag(db_session, unique_name(f"正式{i}")) for i in range(3)]
    db_session.flush()

    plan = ArticleTopicService.resolve_for_save(
        db_session,
        1,
        make_result([tag.name for tag in tags[:candidate_count]]),
    )

    assert plan.active_tag_ids == tuple(tag.id for tag in tags[:expected_count])
    assert plan.pending_tag_id is None


def test_resolve_for_save_skips_invalid_candidates_without_consuming_slots(
    db_session: Session,
) -> None:
    pending = add_tag(db_session, unique_name("待整理"), status="pending")
    foreign = add_tag(db_session, unique_name("外部"), user_id=2)
    first = add_tag(db_session, unique_name("正式一"))
    second = add_tag(db_session, unique_name("正式二"))
    third = add_tag(db_session, unique_name("正式三"))
    db_session.flush()

    plan = ArticleTopicService.resolve_for_save(
        db_session,
        1,
        make_result(
            [
                pending.name,
                foreign.name,
                unique_name("不存在"),
                first.name,
                first.name,
                second.name,
                third.name,
            ]
        ),
    )

    assert plan.active_tag_ids == (first.id, second.id)
    assert plan.pending_tag_id is None


def test_resolve_for_save_handles_active_and_existing_pending_suggestions(
    db_session: Session,
) -> None:
    selected = add_tag(db_session, unique_name("已选正式"))
    other = add_tag(db_session, unique_name("补充正式"))
    pending = add_tag(db_session, unique_name("已有建议"), status="pending")
    db_session.flush()

    same_plan = ArticleTopicService.resolve_for_save(
        db_session, 1, make_result([selected.name], selected.name)
    )
    active_plan = ArticleTopicService.resolve_for_save(
        db_session, 1, make_result([selected.name], other.name)
    )
    pending_plan = ArticleTopicService.resolve_for_save(
        db_session, 1, make_result([selected.name], pending.name)
    )

    assert same_plan == ArticleTopicPlan(active_tag_ids=(selected.id,))
    assert active_plan == ArticleTopicPlan(active_tag_ids=(selected.id, other.id))
    assert pending_plan == ArticleTopicPlan(
        active_tag_ids=(selected.id,), pending_tag_id=pending.id
    )


def test_resolve_for_save_creates_owned_pending_and_ignores_foreign_same_name(
    db_session: Session,
) -> None:
    suggestion = unique_name("新建议")
    foreign = add_tag(db_session, suggestion, user_id=2, status="pending")
    db_session.flush()

    plan = ArticleTopicService.resolve_for_save(
        db_session, 1, make_result(suggested_topic=suggestion)
    )

    own = db_session.scalar(select(Tag).where(Tag.user_id == 1, Tag.name == suggestion))
    assert own is not None
    assert own.id != foreign.id
    assert own.status == "pending"
    assert plan == ArticleTopicPlan(pending_tag_id=own.id)


def test_resolve_for_save_does_not_use_suggestion_after_two_active_topics(
    db_session: Session,
) -> None:
    active = [add_tag(db_session, unique_name(f"正式{i}")) for i in range(2)]
    suggestion = add_tag(db_session, unique_name("不应补入"))
    db_session.flush()

    plan = ArticleTopicService.resolve_for_save(
        db_session,
        1,
        make_result([tag.name for tag in active], suggestion.name),
    )

    assert plan == ArticleTopicPlan(active_tag_ids=tuple(tag.id for tag in active))


def test_replace_article_topics_replaces_owned_links_and_cleans_only_orphan_pending(
    db_session: Session,
) -> None:
    article = create_article(db_session)
    shared_article = create_article(db_session)
    old_active = add_tag(db_session, unique_name("旧正式"))
    orphan_pending = add_tag(db_session, unique_name("孤立建议"), status="pending")
    shared_pending = add_tag(db_session, unique_name("共享建议"), status="pending")
    new_active = add_tag(db_session, unique_name("新正式"))
    new_pending = add_tag(db_session, unique_name("新建议"), status="pending")
    foreign = add_tag(db_session, unique_name("外部异常"), user_id=2)
    db_session.add_all(
        [
            ArticleTag(article_id=article.id, tag_id=old_active.id),
            ArticleTag(article_id=article.id, tag_id=orphan_pending.id),
            ArticleTag(article_id=article.id, tag_id=shared_pending.id),
            ArticleTag(article_id=shared_article.id, tag_id=shared_pending.id),
            ArticleTag(article_id=article.id, tag_id=foreign.id),
        ]
    )
    db_session.flush()

    ArticleTopicService.replace_article_topics(
        db_session,
        article.user_id,
        article,
        ArticleTopicPlan(
            active_tag_ids=(new_active.id,), pending_tag_id=new_pending.id
        ),
    )
    db_session.flush()

    assert linked_tag_ids(db_session, article.id) == sorted(
        [new_active.id, new_pending.id, foreign.id]
    )
    assert db_session.get(Tag, orphan_pending.id) is None
    assert db_session.get(Tag, shared_pending.id) is not None
    assert db_session.get(Tag, old_active.id) is not None
    assert db_session.get(ArticleTag, (shared_article.id, shared_pending.id)) is not None


@pytest.mark.parametrize("active_count", [0, 1, 2, 3])
def test_replace_article_topics_supports_zero_to_two_active_links(
    db_session: Session,
    active_count: int,
) -> None:
    article = create_article(db_session)
    active = [add_tag(db_session, unique_name(f"替换正式{i}")) for i in range(3)]
    db_session.flush()

    ArticleTopicService.replace_article_topics(
        db_session,
        article.user_id,
        article,
        ArticleTopicPlan(active_tag_ids=tuple(tag.id for tag in active[:active_count])),
    )
    db_session.flush()

    assert linked_tag_ids(db_session, article.id) == sorted(
        tag.id for tag in active[: min(active_count, 2)]
    )


def test_replace_article_topics_ignores_invalid_plan_ids(db_session: Session) -> None:
    article = create_article(db_session)
    own_active = add_tag(db_session, unique_name("有效正式"))
    own_pending = add_tag(db_session, unique_name("有效建议"), status="pending")
    foreign_active = add_tag(db_session, unique_name("外部正式"), user_id=2)
    wrong_pending = add_tag(db_session, unique_name("状态错误"))
    db_session.flush()

    ArticleTopicService.replace_article_topics(
        db_session,
        article.user_id,
        article,
        ArticleTopicPlan(
            active_tag_ids=(own_active.id, foreign_active.id, own_pending.id),
            pending_tag_id=wrong_pending.id,
        ),
    )
    db_session.flush()

    assert linked_tag_ids(db_session, article.id) == [own_active.id]


def test_apply_ai_topic_result_commits_summary_and_topics_together(
    db_session: Session,
) -> None:
    article = create_article(db_session)
    active = add_tag(db_session, unique_name("正式"))
    db_session.commit()

    ArticleService._apply_ai_topic_result(
        db_session,
        article,
        article.user_id,
        make_result([active.name], unique_name("建议")),
    )
    db_session.expire_all()

    saved = db_session.get(Article, article.id)
    assert saved is not None
    assert saved.one_sentence_summary == "新的一句话摘要"
    assert saved.key_points == ["新要点一", "新要点二"]
    assert saved.detailed_summary == "新的详细摘要"
    assert saved.ai_status == "completed"
    assert saved.embedding_status == "pending"
    assert len(linked_tag_ids(db_session, article.id)) == 2


def test_apply_ai_topic_result_rolls_back_summary_topics_and_new_pending(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = create_article(db_session)
    old_active = add_tag(db_session, unique_name("旧正式"))
    old_pending = add_tag(db_session, unique_name("旧建议"), status="pending")
    db_session.add_all(
        [
            ArticleTag(article_id=article.id, tag_id=old_active.id),
            ArticleTag(article_id=article.id, tag_id=old_pending.id),
        ]
    )
    db_session.commit()
    suggestion = unique_name("回滚建议")
    invalid_tag_name = unique_name("约束失败")
    original_replace = ArticleTopicService.replace_article_topics

    def fail_after_replace(
        session: Session,
        current_user_id: int,
        target: Article,
        plan: ArticleTopicPlan,
    ) -> None:
        original_replace(session, current_user_id, target, plan)
        session.flush()
        session.execute(
            text(
                "INSERT INTO tags (user_id, name, status) "
                "VALUES (:user_id, :name, 'invalid')"
            ),
            {"user_id": target.user_id, "name": invalid_tag_name},
        )

    monkeypatch.setattr(
        ArticleTopicService,
        "replace_article_topics",
        staticmethod(fail_after_replace),
    )

    with pytest.raises(SQLAlchemyError):
        ArticleService._apply_ai_topic_result(
            db_session,
            article,
            article.user_id,
            make_result(suggested_topic=suggestion),
        )

    db_session.expire_all()
    saved = db_session.get(Article, article.id)
    assert saved is not None
    assert saved.one_sentence_summary == "旧的一句话摘要"
    assert saved.key_points == ["旧要点"]
    assert saved.detailed_summary == "旧的详细摘要"
    assert saved.ai_status == "processing"
    assert saved.embedding_status == "completed"
    assert linked_tag_ids(db_session, article.id) == sorted(
        [old_active.id, old_pending.id]
    )
    assert db_session.get(Tag, old_pending.id) is not None
    assert db_session.scalar(
        select(Tag.id).where(Tag.user_id == 1, Tag.name == suggestion)
    ) is None


@pytest.mark.parametrize(
    ("promote_while_waiting", "fill_active_slots", "expected_kind"),
    [(False, False, "pending"), (True, False, "active"), (True, True, "ignored")],
)
def test_concurrent_suggestion_requeries_latest_state(
    promote_while_waiting: bool,
    fill_active_slots: bool,
    expected_kind: str,
) -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    suggestion = unique_name("并发建议")
    selected_names: list[str] = []
    with SessionLocal() as setup:
        if fill_active_slots:
            selected = [
                Tag(user_id=user_id, name=unique_name(f"已选{i}"), status="active")
                for i in range(2)
            ]
            setup.add_all(selected)
            setup.commit()
            selected_names = [tag.name for tag in selected]

    backend_pids: Queue[int] = Queue(maxsize=1)

    def resolve_in_second_session() -> tuple[ArticleTopicPlan, int]:
        with SessionLocal() as second:
            backend_pid = second.scalar(text("SELECT pg_backend_pid()"))
            assert backend_pid is not None
            backend_pids.put(backend_pid)
            plan = ArticleTopicService.resolve_for_save(
                second,
                user_id,
                make_result(selected_names, suggestion),
            )
            second.commit()
            return plan, backend_pid

    tag_id: int | None = None
    try:
        with SessionLocal() as first, ThreadPoolExecutor(max_workers=1) as pool:
            first_plan = ArticleTopicService.resolve_for_save(
                first,
                user_id,
                make_result([], suggestion),
            )
            assert first_plan.pending_tag_id is not None
            tag_id = first_plan.pending_tag_id
            future = pool.submit(resolve_in_second_session)
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
                                "AND wait_event_type = 'Lock' AND query LIKE '%INSERT INTO tags%')"
                            ),
                            {"pid": second_pid},
                        )
                    )
                if blocked:
                    break
                sleep(0.02)
            assert blocked, "第二个会话未等待标签唯一约束冲突"
            if promote_while_waiting:
                tag = first.get(Tag, tag_id)
                assert tag is not None
                tag.status = "active"
                first.flush()
            first.commit()
            second_plan, _ = future.result(timeout=5)

        if expected_kind == "pending":
            assert second_plan.pending_tag_id == tag_id
        elif expected_kind == "active":
            assert tag_id in second_plan.active_tag_ids
            assert second_plan.pending_tag_id is None
        else:
            assert len(second_plan.active_tag_ids) == 2
            assert tag_id not in second_plan.active_tag_ids
            assert second_plan.pending_tag_id is None
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(
                delete(ArticleTag).where(
                    ArticleTag.tag_id.in_(select(Tag.id).where(Tag.user_id == user_id))
                )
            )
            cleanup.execute(delete(Article).where(Article.user_id == user_id))
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()


def test_two_active_topics_and_one_pending_are_saved_together(
    db_session: Session,
) -> None:
    article = create_article(db_session)
    active = [add_tag(db_session, unique_name(f"双正式{i}")) for i in range(2)]
    pending = add_tag(db_session, unique_name("并存建议"), status="pending")
    db_session.flush()

    result = make_result([tag.name for tag in active], pending.name)
    plan = ArticleTopicService.resolve_for_save(db_session, article.user_id, result)
    ArticleTopicService.replace_article_topics(
        db_session,
        article.user_id,
        article,
        plan,
    )
    db_session.flush()

    assert plan == ArticleTopicPlan(
        active_tag_ids=tuple(tag.id for tag in active),
        pending_tag_id=pending.id,
    )
    assert linked_tag_ids(db_session, article.id) == sorted(
        [tag.id for tag in active] + [pending.id]
    )


def test_apply_topic_result_rejects_foreign_article_before_any_change(
    db_session: Session,
) -> None:
    foreign_article = create_article(db_session, user_id=2)
    old_active = add_tag(db_session, unique_name("外部旧正式"), user_id=2)
    db_session.add(ArticleTag(article_id=foreign_article.id, tag_id=old_active.id))
    db_session.commit()

    with pytest.raises(ArticleNotFoundError):
        ArticleService._apply_ai_topic_result(
            db_session,
            foreign_article,
            1,
            make_result(suggested_topic=unique_name("不应创建")),
        )

    db_session.expire_all()
    saved = db_session.get(Article, foreign_article.id)
    assert saved is not None
    assert saved.one_sentence_summary == "旧的一句话摘要"
    assert saved.ai_status == "processing"
    assert linked_tag_ids(db_session, foreign_article.id) == [old_active.id]
    assert db_session.scalar(select(Tag.id).where(Tag.user_id == 1)) is None


def test_non_sqlalchemy_failure_rolls_back_all_topic_changes(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = create_article(db_session)
    old_active = add_tag(db_session, unique_name("异常旧正式"))
    db_session.add(ArticleTag(article_id=article.id, tag_id=old_active.id))
    db_session.commit()
    suggestion = unique_name("异常新建议")
    original_replace = ArticleTopicService.replace_article_topics

    def fail_after_replace(*args: object, **kwargs: object) -> None:
        original_replace(*args, **kwargs)
        db_session.flush()
        raise RuntimeError("注入普通 Python 异常")

    monkeypatch.setattr(ArticleTopicService, "replace_article_topics", fail_after_replace)

    with pytest.raises(RuntimeError, match="普通 Python 异常"):
        ArticleService._apply_ai_topic_result(
            db_session,
            article,
            article.user_id,
            make_result(suggested_topic=suggestion),
        )

    db_session.expire_all()
    saved = db_session.get(Article, article.id)
    assert saved is not None
    assert saved.one_sentence_summary == "旧的一句话摘要"
    assert linked_tag_ids(db_session, article.id) == [old_active.id]
    assert db_session.scalar(
        select(Tag.id).where(Tag.user_id == article.user_id, Tag.name == suggestion)
    ) is None


def test_successful_topic_commit_refreshes_cached_tags_before_commit(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = create_article(db_session)
    old_active = add_tag(db_session, unique_name("缓存旧正式"))
    new_active = add_tag(db_session, unique_name("缓存新正式"))
    db_session.add(ArticleTag(article_id=article.id, tag_id=old_active.id))
    db_session.commit()
    db_session.refresh(article)
    assert [tag.id for tag in article.tags] == [old_active.id]
    commit_started = False
    original_commit = ArticleService._commit
    original_expire = db_session.expire

    def track_commit(session: Session) -> None:
        nonlocal commit_started
        commit_started = True
        original_commit(session)

    def expire_before_commit(*args: object, **kwargs: object) -> None:
        assert not commit_started, "关系缓存不能在 commit 成功后才失效"
        original_expire(*args, **kwargs)

    monkeypatch.setattr(ArticleService, "_commit", staticmethod(track_commit))
    monkeypatch.setattr(db_session, "expire", expire_before_commit)

    ArticleService._apply_ai_topic_result(
        db_session,
        article,
        article.user_id,
        make_result([new_active.name]),
    )

    assert article.one_sentence_summary == "新的一句话摘要"
    assert article.ai_status == "completed"
    assert [tag.id for tag in article.tags] == [new_active.id]


def _run_with_synchronized_first_tag_lock(
    barrier: Barrier,
    operation,
    tag_only: bool = True,
):
    with engine.connect() as connection:
        synchronized = False

        def synchronize_first_lock(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            nonlocal synchronized
            normalized = statement.upper()
            if synchronized or "FOR UPDATE" not in normalized:
                return
            if tag_only and "TAGS" not in normalized:
                return
            synchronized = True
            barrier.wait(timeout=5)

        event.listen(connection, "before_cursor_execute", synchronize_first_lock)
        try:
            with Session(bind=connection, autoflush=False, expire_on_commit=False) as session:
                session.execute(text("SET LOCAL lock_timeout = '3s'"))
                result = operation(session)
                session.commit()
                return result
        finally:
            event.remove(connection, "before_cursor_execute", synchronize_first_lock)


def test_reverse_candidate_orders_use_one_stable_tag_lock_order() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        first = Tag(user_id=user_id, name=unique_name("反序一"), status="active")
        second = Tag(user_id=user_id, name=unique_name("反序二"), status="active")
        setup.add_all([first, second])
        setup.commit()
        names = (first.name, second.name)

    barrier = Barrier(2)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    _run_with_synchronized_first_tag_lock,
                    barrier,
                    lambda session, ordered=ordered: ArticleTopicService.resolve_for_save(
                        session, user_id, make_result(list(ordered))
                    ),
                )
                for ordered in (names, tuple(reversed(names)))
            ]
            plans = [future.result(timeout=10) for future in futures]
        assert all(len(plan.active_tag_ids) == 2 for plan in plans)
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()


def test_merge_and_topic_resolution_share_stable_tag_lock_order() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        pending = Tag(user_id=user_id, name=unique_name("归入来源"), status="pending")
        target = Tag(user_id=user_id, name=unique_name("归入目标"), status="active")
        setup.add_all([pending, target])
        setup.commit()
        pending_id = pending.id
        target_id = target.id
        pending_name = pending.name
        target_name = target.name

    barrier = Barrier(2)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            topic_future = pool.submit(
                _run_with_synchronized_first_tag_lock,
                barrier,
                lambda session: ArticleTopicService.resolve_for_save(
                    session,
                    user_id,
                    make_result([target_name], pending_name),
                ),
            )
            merge_future = pool.submit(
                _run_with_synchronized_first_tag_lock,
                barrier,
                lambda session: TagService.merge_pending(
                    session, pending_id, target_id, user_id
                ),
            )
            topic_future.result(timeout=10)
            merge_future.result(timeout=10)
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(
                delete(ArticleTag).where(
                    ArticleTag.tag_id.in_(select(Tag.id).where(Tag.user_id == user_id))
                )
            )
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()


def test_merge_and_article_topic_save_share_article_then_tag_lock_order() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        article = create_article(setup, user_id=user_id)
        pending = Tag(user_id=user_id, name=unique_name("保存归入来源"), status="pending")
        target = Tag(user_id=user_id, name=unique_name("保存归入目标"), status="active")
        setup.add_all([pending, target])
        setup.flush()
        setup.add(ArticleTag(article_id=article.id, tag_id=pending.id))
        setup.commit()
        article_id = article.id
        pending_id = pending.id
        target_id = target.id
        pending_name = pending.name
        target_name = target.name

    barrier = Barrier(2)

    def save_topics(session: Session) -> None:
        article = session.get(Article, article_id)
        assert article is not None
        ArticleService._apply_ai_topic_result(
            session,
            article,
            user_id,
            make_result([target_name], pending_name),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            save_future = pool.submit(
                _run_with_synchronized_first_tag_lock,
                barrier,
                save_topics,
                False,
            )
            merge_future = pool.submit(
                _run_with_synchronized_first_tag_lock,
                barrier,
                lambda session: TagService.merge_pending(
                    session, pending_id, target_id, user_id
                ),
                False,
            )
            save_future.result(timeout=10)
            merge_future.result(timeout=10)
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(delete(ArticleTag).where(ArticleTag.article_id == article_id))
            cleanup.execute(delete(Article).where(Article.user_id == user_id))
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()


def test_concurrent_pending_reuse_survives_orphan_cleanup() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        first_article = create_article(setup, user_id=user_id)
        second_article = create_article(setup, user_id=user_id)
        pending = Tag(user_id=user_id, name=unique_name("并发保留"), status="pending")
        setup.add(pending)
        setup.flush()
        setup.add(ArticleTag(article_id=first_article.id, tag_id=pending.id))
        setup.commit()
        first_article_id = first_article.id
        second_article_id = second_article.id
        pending_id = pending.id

    backend_pids: Queue[int] = Queue(maxsize=1)

    def clean_old_link() -> int:
        with SessionLocal() as cleanup_session:
            backend_pid = cleanup_session.scalar(text("SELECT pg_backend_pid()"))
            assert backend_pid is not None
            backend_pids.put(backend_pid)
            article = cleanup_session.get(Article, first_article_id)
            assert article is not None
            ArticleTopicService.replace_article_topics(
                cleanup_session,
                user_id,
                article,
                ArticleTopicPlan(),
            )
            cleanup_session.commit()
            return backend_pid

    try:
        with SessionLocal() as association, ThreadPoolExecutor(max_workers=1) as pool:
            article = association.get(Article, second_article_id)
            assert article is not None
            ArticleTopicService.replace_article_topics(
                association,
                user_id,
                article,
                ArticleTopicPlan(pending_tag_id=pending_id),
            )
            future = pool.submit(clean_old_link)
            cleanup_pid = backend_pids.get(timeout=5)
            deadline = monotonic() + 5
            blocked_on_tag_lock = False
            while monotonic() < deadline:
                with SessionLocal() as observer:
                    blocked_on_tag_lock = bool(
                        observer.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE pid = :pid AND datname = current_database() "
                                "AND wait_event_type = 'Lock' "
                                "AND query LIKE '%tags%' AND query LIKE '%FOR UPDATE%')"
                            ),
                            {"pid": cleanup_pid},
                        )
                    )
                if blocked_on_tag_lock:
                    break
                sleep(0.02)
            association.commit()
            future.result(timeout=10)
            assert blocked_on_tag_lock, "孤立清理没有等待 pending 标签行锁"

        with SessionLocal() as verify:
            assert verify.get(Tag, pending_id) is not None
            assert verify.get(ArticleTag, (second_article_id, pending_id)) is not None
            assert verify.get(ArticleTag, (first_article_id, pending_id)) is None
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(
                delete(ArticleTag).where(
                    ArticleTag.article_id.in_([first_article_id, second_article_id])
                )
            )
            cleanup.execute(delete(Article).where(Article.user_id == user_id))
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()


def test_merge_retries_with_complete_article_set_before_locking_tags() -> None:
    user_id = int(uuid4().int % 10**12) + 10**12
    with SessionLocal() as setup:
        first_article = create_article(setup, user_id=user_id)
        second_article = create_article(setup, user_id=user_id)
        pending = Tag(user_id=user_id, name=unique_name("稳定集合来源"), status="pending")
        target = Tag(user_id=user_id, name=unique_name("稳定集合目标"), status="active")
        setup.add_all([pending, target])
        setup.flush()
        setup.add(ArticleTag(article_id=first_article.id, tag_id=pending.id))
        setup.commit()
        first_article_id = first_article.id
        second_article_id = second_article.id
        pending_id = pending.id
        target_id = target.id

    first_article_lock_acquired = Event()
    association_committed = Event()
    lock_sequence: list[tuple[str, set[int]]] = []
    rollback_count = 0
    commit_count = 0

    def run_merge() -> dict[str, int]:
        nonlocal rollback_count, commit_count
        with engine.connect() as connection:
            paused = False

            def observe_locks(
                _connection,
                _cursor,
                statement: str,
                parameters,
                _context,
                _executemany,
            ) -> None:
                nonlocal paused
                normalized = statement.upper()
                if "FOR UPDATE" not in normalized:
                    return
                values = set(parameters.values()) if isinstance(parameters, dict) else set(parameters)
                if "FROM ARTICLES" in normalized:
                    locked_ids = {first_article_id, second_article_id} & values
                    lock_sequence.append(("article", locked_ids))
                    if not paused:
                        paused = True
                        first_article_lock_acquired.set()
                        assert association_committed.wait(timeout=5)
                elif "FROM TAGS" in normalized:
                    locked_ids = {pending_id, target_id} & values
                    lock_sequence.append(("tag", locked_ids))

            event.listen(connection, "after_cursor_execute", observe_locks)
            try:
                with Session(bind=connection, autoflush=False, expire_on_commit=False) as session:
                    event.listen(
                        session,
                        "after_rollback",
                        lambda _session: _record_rollback(),
                    )
                    event.listen(
                        session,
                        "after_commit",
                        lambda _session: _record_commit(),
                    )
                    return TagService.merge_pending(
                        session,
                        pending_id,
                        target_id,
                        user_id,
                    )
            finally:
                event.remove(connection, "after_cursor_execute", observe_locks)

    def _record_rollback() -> None:
        nonlocal rollback_count
        rollback_count += 1

    def _record_commit() -> None:
        nonlocal commit_count
        commit_count += 1

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_merge)
            assert first_article_lock_acquired.wait(timeout=5)
            try:
                with SessionLocal() as association:
                    article = association.get(Article, second_article_id)
                    assert article is not None
                    ArticleTopicService.replace_article_topics(
                        association,
                        user_id,
                        article,
                        ArticleTopicPlan(pending_tag_id=pending_id),
                    )
                    association.commit()
            finally:
                association_committed.set()
            result = future.result(timeout=10)

        assert result["affected_article_count"] == 2
        assert rollback_count == 1
        assert commit_count == 1
        assert lock_sequence == [
            ("article", {first_article_id}),
            ("tag", {pending_id, target_id}),
            ("article", {first_article_id, second_article_id}),
            ("tag", {pending_id, target_id}),
        ]
        with SessionLocal() as verify:
            assert verify.get(Tag, pending_id) is None
            assert verify.get(ArticleTag, (first_article_id, target_id)) is not None
            assert verify.get(ArticleTag, (second_article_id, target_id)) is not None
    finally:
        association_committed.set()
        with SessionLocal() as cleanup:
            cleanup.execute(
                delete(ArticleTag).where(
                    ArticleTag.article_id.in_([first_article_id, second_article_id])
                )
            )
            cleanup.execute(delete(Article).where(Article.user_id == user_id))
            cleanup.execute(delete(Tag).where(Tag.user_id == user_id))
            cleanup.commit()
