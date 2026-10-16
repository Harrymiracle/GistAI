from dataclasses import dataclass

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai.schemas import AIArticleTopicResult
from app.core.exceptions import ArticleNotFoundError
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag


@dataclass(frozen=True)
class ArticleTopicPlan:
    """文章主题保存前的已校验计划。"""

    active_tag_ids: tuple[int, ...] = ()
    pending_tag_id: int | None = None


class ArticleTopicService:
    """根据当前标签状态解析并替换文章主题关联。"""

    MAX_ACTIVE_TOPICS = 2

    @staticmethod
    def list_active_names(session: Session, user_id: int) -> list[str]:
        """按稳定顺序返回当前用户可供 AI 选择的正式主题。"""

        return list(
            session.scalars(
                select(Tag.name)
                .where(Tag.user_id == user_id, Tag.status == "active")
                .order_by(Tag.name.collate("C"), Tag.id)
            )
        )

    @classmethod
    def resolve_for_save(
        cls,
        session: Session,
        user_id: int,
        result: AIArticleTopicResult,
        additional_tag_ids: tuple[int, ...] = (),
    ) -> ArticleTopicPlan:
        """按数据库最新状态解析 AI 候选，不在服务内部提交事务。"""

        candidate_names: list[str] = []
        seen_candidates: set[str] = set()
        for raw_name in result.topics:
            name = raw_name.strip()
            if not name or name in seen_candidates:
                continue
            seen_candidates.add(name)
            candidate_names.append(name)

        suggestion = result.suggested_topic
        suggestion = suggestion.strip() if suggestion is not None else None
        if suggestion:
            session.scalar(
                pg_insert(Tag)
                .values(user_id=user_id, name=suggestion, status="pending")
                .on_conflict_do_nothing(index_elements=[Tag.user_id, Tag.name])
                .returning(Tag.id)
            )

        relevant_names = list(candidate_names)
        if suggestion and suggestion not in seen_candidates:
            relevant_names.append(suggestion)
        existing_ids: tuple[int, ...] = ()
        if relevant_names:
            existing_ids = tuple(
                session.scalars(
                    select(Tag.id).where(
                        Tag.user_id == user_id,
                        Tag.name.in_(relevant_names),
                    )
                )
            )
        locked_tags = cls.lock_tags_by_id(
            session,
            user_id,
            (*existing_ids, *additional_tag_ids),
        )
        tags_by_name = {tag.name: tag for tag in locked_tags}

        selected_ids: list[int] = []
        selected_names: set[str] = set()
        for name in candidate_names:
            tag = tags_by_name.get(name)
            if tag is None or tag.status != "active":
                continue
            selected_ids.append(tag.id)
            selected_names.add(tag.name)
            if len(selected_ids) == cls.MAX_ACTIVE_TOPICS:
                break

        if not suggestion or suggestion in selected_names:
            return ArticleTopicPlan(active_tag_ids=tuple(selected_ids))
        suggested_tag = tags_by_name.get(suggestion)
        if suggested_tag is None:
            return ArticleTopicPlan(active_tag_ids=tuple(selected_ids))
        if suggested_tag.status == "active":
            if (
                len(selected_ids) < cls.MAX_ACTIVE_TOPICS
                and suggested_tag.id not in selected_ids
            ):
                selected_ids.append(suggested_tag.id)
            return ArticleTopicPlan(active_tag_ids=tuple(selected_ids))
        if suggested_tag.status == "pending":
            return ArticleTopicPlan(
                active_tag_ids=tuple(selected_ids),
                pending_tag_id=suggested_tag.id,
            )
        return ArticleTopicPlan(active_tag_ids=tuple(selected_ids))

    @staticmethod
    def get_owned_article_for_update(
        session: Session,
        article_id: int,
        user_id: int,
    ) -> Article:
        """按认证用户锁定文章，拒绝仅信任传入对象的归属字段。"""

        article = session.scalar(
            select(Article)
            .where(Article.id == article_id, Article.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if article is None:
            raise ArticleNotFoundError()
        return article

    @staticmethod
    def list_pending_tag_ids(
        session: Session,
        article_id: int,
        user_id: int,
    ) -> tuple[int, ...]:
        """返回文章当前关联的本用户 pending ID。"""

        return tuple(
            session.scalars(
                select(Tag.id)
                .join(ArticleTag, ArticleTag.tag_id == Tag.id)
                .where(
                    ArticleTag.article_id == article_id,
                    Tag.user_id == user_id,
                    Tag.status == "pending",
                )
                .order_by(Tag.id)
            )
        )

    @staticmethod
    def lock_tags_by_id(
        session: Session,
        user_id: int,
        tag_ids: tuple[int, ...],
    ) -> list[Tag]:
        """按 Tag.id 升序锁定当前用户标签并读取最新状态。"""

        unique_ids = tuple(sorted(set(tag_ids)))
        if not unique_ids:
            return []
        return list(
            session.scalars(
                select(Tag)
                .where(Tag.user_id == user_id, Tag.id.in_(unique_ids))
                .order_by(Tag.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    def replace_article_topics(
        session: Session,
        user_id: int,
        article: Article,
        plan: ArticleTopicPlan,
    ) -> None:
        """原子替换文章自己的主题关联，并清理失去引用的旧建议。"""

        owned_article = ArticleTopicService.get_owned_article_for_update(
            session,
            article.id,
            user_id,
        )
        old_pending_ids = ArticleTopicService.list_pending_tag_ids(
            session,
            owned_article.id,
            user_id,
        )

        requested_active_ids = tuple(dict.fromkeys(plan.active_tag_ids))
        requested_ids = (*old_pending_ids, *requested_active_ids)
        if plan.pending_tag_id is not None:
            requested_ids = (*requested_ids, plan.pending_tag_id)
        locked_tags = ArticleTopicService.lock_tags_by_id(
            session,
            user_id,
            requested_ids,
        )
        tags_by_id = {tag.id: tag for tag in locked_tags}

        old_pending_ids = ArticleTopicService.list_pending_tag_ids(
            session,
            owned_article.id,
            user_id,
        )
        valid_active_ids = {
            tag_id
            for tag_id, tag in tags_by_id.items()
            if tag.status == "active"
        }
        ordered_active_ids: list[int] = []
        for tag_id in requested_active_ids:
            if tag_id not in valid_active_ids:
                continue
            ordered_active_ids.append(tag_id)
            if len(ordered_active_ids) == ArticleTopicService.MAX_ACTIVE_TOPICS:
                break

        valid_pending_id: int | None = None
        if plan.pending_tag_id is not None:
            pending = tags_by_id.get(plan.pending_tag_id)
            if pending is not None and pending.status == "pending":
                valid_pending_id = pending.id

        own_tag_ids = select(Tag.id).where(Tag.user_id == user_id)
        session.execute(
            delete(ArticleTag).where(
                ArticleTag.article_id == owned_article.id,
                ArticleTag.tag_id.in_(own_tag_ids),
            )
        )

        replacement_ids = list(ordered_active_ids)
        if valid_pending_id is not None and valid_pending_id not in replacement_ids:
            replacement_ids.append(valid_pending_id)
        if replacement_ids:
            session.execute(
                pg_insert(ArticleTag)
                .values(
                    [
                        {"article_id": article.id, "tag_id": tag_id}
                        for tag_id in replacement_ids
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=[ArticleTag.article_id, ArticleTag.tag_id]
                )
            )

        session.flush()
        if old_pending_ids:
            session.execute(
                delete(Tag).where(
                    Tag.id.in_(old_pending_ids),
                    Tag.user_id == user_id,
                    Tag.status == "pending",
                    ~exists(
                        select(ArticleTag.article_id).where(
                            ArticleTag.tag_id == Tag.id
                        )
                    ),
                )
            )
