from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    TagAlreadyExistsError,
    TagAssociationConflictError,
    TagMergeConcurrentConflictError,
    TagNotFoundError,
    TagStatusConflictError,
)
from app.models.article import Article
from app.models.article_tag import ArticleTag
from app.models.tag import Tag


class _MergeArticleSetChanged(Exception):
    """本轮归入操作锁定的文章集合已经过期。"""


class TagService:
    """当前用户的 Tag CRUD 业务。"""

    MERGE_MAX_ATTEMPTS = 3

    @staticmethod
    def list_tags(session: Session, user_id: int) -> list[tuple[Tag, int]]:
        """按当前用户文章数量和固定名称顺序返回正式主题。"""

        return list(
            session.execute(
                select(Tag, func.count(Article.id).label("article_count"))
                .outerjoin(ArticleTag, ArticleTag.tag_id == Tag.id)
                .outerjoin(
                    Article,
                    (Article.id == ArticleTag.article_id) & (Article.user_id == user_id),
                )
                .where(Tag.user_id == user_id, Tag.status == "active")
                .group_by(Tag.id)
                .order_by(func.count(Article.id).desc(), Tag.name.collate("C"), Tag.id)
            ).all()
        )

    @staticmethod
    def count_articles(session: Session, tag_id: int, user_id: int) -> int:
        """仅统计当前用户文章。"""

        return session.scalar(
            select(func.count(Article.id))
            .join(ArticleTag, ArticleTag.article_id == Article.id)
            .where(ArticleTag.tag_id == tag_id, Article.user_id == user_id)
        ) or 0

    @staticmethod
    def list_pending(
        session: Session, user_id: int
    ) -> list[tuple[Tag, list[tuple[int, str | None]]]]:
        """按创建时间返回待整理主题和当前用户来源文章。"""

        tags = list(session.scalars(
            select(Tag)
            .where(Tag.user_id == user_id, Tag.status == "pending")
            .order_by(Tag.created_at.desc(), Tag.id.desc())
        ).all())
        if not tags:
            return []
        sources: dict[int, list[tuple[int, str | None]]] = {tag.id: [] for tag in tags}
        rows = session.execute(
            select(ArticleTag.tag_id, Article.id, Article.title)
            .join(Article, Article.id == ArticleTag.article_id)
            .where(ArticleTag.tag_id.in_(sources), Article.user_id == user_id)
            .order_by(Article.id)
        )
        for tag_id, article_id, title in rows:
            sources[tag_id].append((article_id, title))
        return [(tag, sources[tag.id]) for tag in tags]

    @classmethod
    def create_tag(cls, session: Session, user_id: int, name: str) -> Tag:
        existing_id = cls._find_tag_id_by_name(session, user_id, name)
        if existing_id is not None:
            raise TagAlreadyExistsError(existing_id)

        tag = Tag(user_id=user_id, name=name, status="active")
        session.add(tag)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = cls._find_tag_id_by_name(session, user_id, name)
            if existing_id is not None:
                raise TagAlreadyExistsError(existing_id) from None
            raise
        except SQLAlchemyError:
            session.rollback()
            raise

        session.refresh(tag)
        return tag

    @classmethod
    def update_tag(
        cls,
        session: Session,
        tag_id: int,
        user_id: int,
        name: str,
    ) -> Tag:
        tag = cls.get_tag(session, tag_id, user_id)
        if tag.status != "active":
            raise TagStatusConflictError()
        existing_id = cls._find_tag_id_by_name(session, user_id, name)
        if existing_id is not None and existing_id != tag.id:
            raise TagAlreadyExistsError(existing_id)

        tag.name = name
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = cls._find_tag_id_by_name(session, user_id, name)
            if existing_id is not None and existing_id != tag_id:
                raise TagAlreadyExistsError(existing_id) from None
            raise
        except SQLAlchemyError:
            session.rollback()
            raise

        session.refresh(tag)
        return tag

    @classmethod
    def delete_tag(cls, session: Session, tag_id: int, user_id: int) -> int:
        try:
            tag = cls._get_locked_tag(session, tag_id, user_id)
            if tag.status != "active":
                raise TagStatusConflictError()
            cls._ensure_no_foreign_association(session, tag.id, user_id)
            session.delete(tag)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return tag_id

    @staticmethod
    def get_tag(session: Session, tag_id: int, user_id: int) -> Tag:
        tag = session.scalar(
            select(Tag).where(
                Tag.id == tag_id,
                Tag.user_id == user_id,
            )
        )
        if tag is None:
            raise TagNotFoundError()
        return tag

    @classmethod
    def get_active_tag(cls, session: Session, tag_id: int, user_id: int) -> Tag:
        tag = cls.get_tag(session, tag_id, user_id)
        if tag.status != "active":
            raise TagNotFoundError()
        return tag

    @staticmethod
    def _get_locked_tag(session: Session, tag_id: int, user_id: int) -> Tag:
        tag = session.scalar(
            select(Tag)
            .where(Tag.id == tag_id, Tag.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if tag is None:
            raise TagNotFoundError()
        return tag

    @classmethod
    def _get_locked_pending(cls, session: Session, tag_id: int, user_id: int) -> Tag:
        tag = cls._get_locked_tag(session, tag_id, user_id)
        if tag.status != "pending":
            raise TagStatusConflictError()
        return tag

    @staticmethod
    def _ensure_no_foreign_association(
        session: Session, tag_id: int, user_id: int
    ) -> None:
        """在标签行已锁定时拒绝跨用户文章关联。"""

        foreign_article_id = session.scalar(
            select(ArticleTag.article_id)
            .join(Article, Article.id == ArticleTag.article_id)
            .where(ArticleTag.tag_id == tag_id, Article.user_id != user_id)
            .limit(1)
        )
        if foreign_article_id is not None:
            raise TagAssociationConflictError()

    @classmethod
    def promote_pending(cls, session: Session, tag_id: int, user_id: int) -> Tag:
        tag = cls._get_locked_pending(session, tag_id, user_id)
        name = tag.name
        tag.status = "active"
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = session.scalar(
                select(Tag.id).where(
                    Tag.user_id == user_id, Tag.name == name, Tag.status == "active"
                )
            )
            if existing_id is not None:
                raise TagAlreadyExistsError(existing_id) from None
            raise TagStatusConflictError() from None
        except Exception:
            session.rollback()
            raise
        session.refresh(tag)
        return tag

    @classmethod
    def merge_pending(
        cls, session: Session, tag_id: int, target_tag_id: int, user_id: int
    ) -> dict[str, int]:
        for _attempt in range(cls.MERGE_MAX_ATTEMPTS):
            try:
                return cls._merge_pending_once(
                    session,
                    tag_id,
                    target_tag_id,
                    user_id,
                )
            except _MergeArticleSetChanged:
                session.rollback()
            except Exception:
                session.rollback()
                raise
        raise TagMergeConcurrentConflictError()

    @staticmethod
    def _list_merge_article_ids(
        session: Session,
        tag_id: int,
        user_id: int,
    ) -> tuple[int, ...]:
        """按固定顺序读取来源待整理主题的当前文章集合。"""

        return tuple(
            session.scalars(
                select(Article.id)
                .join(ArticleTag, ArticleTag.article_id == Article.id)
                .where(
                    ArticleTag.tag_id == tag_id,
                    Article.user_id == user_id,
                )
                .order_by(Article.id)
            )
        )

    @classmethod
    def _merge_pending_once(
        cls,
        session: Session,
        tag_id: int,
        target_tag_id: int,
        user_id: int,
    ) -> dict[str, int]:
        """仅在文章集合稳定时完成一次归入事务。"""

        discovered_article_ids = cls._list_merge_article_ids(session, tag_id, user_id)
        locked_article_ids: tuple[int, ...] = ()
        if discovered_article_ids:
            locked_article_ids = tuple(
                session.scalars(
                    select(Article.id)
                    .where(
                        Article.user_id == user_id,
                        Article.id.in_(discovered_article_ids),
                    )
                    .order_by(Article.id)
                    .with_for_update()
                )
            )

        locked_tags = list(
            session.scalars(
                select(Tag)
                .where(
                    Tag.user_id == user_id,
                    Tag.id.in_(sorted({tag_id, target_tag_id})),
                )
                .order_by(Tag.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        tags_by_id = {tag.id: tag for tag in locked_tags}
        pending = tags_by_id.get(tag_id)
        target = tags_by_id.get(target_tag_id)
        if pending is None or target is None:
            raise TagNotFoundError()
        if pending.status != "pending":
            raise TagStatusConflictError()
        if target.status != "active":
            raise TagStatusConflictError()

        current_article_ids = cls._list_merge_article_ids(session, pending.id, user_id)
        if current_article_ids != locked_article_ids:
            raise _MergeArticleSetChanged()

        cls._ensure_no_foreign_association(session, pending.id, user_id)
        if current_article_ids:
            statement = pg_insert(ArticleTag).values(
                [
                    {"article_id": article_id, "tag_id": target.id}
                    for article_id in current_article_ids
                ]
            )
            session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[ArticleTag.article_id, ArticleTag.tag_id]
                )
            )
        session.delete(pending)
        session.commit()
        return {
            "tag_id": tag_id,
            "target_tag_id": target_tag_id,
            "affected_article_count": len(current_article_ids),
        }

    @classmethod
    def ignore_pending(cls, session: Session, tag_id: int, user_id: int) -> dict[str, int]:
        try:
            pending = cls._get_locked_pending(session, tag_id, user_id)
            cls._ensure_no_foreign_association(session, pending.id, user_id)
            article_count = cls.count_articles(session, tag_id, user_id)
            session.delete(pending)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"tag_id": tag_id, "affected_article_count": article_count}

    @staticmethod
    def _find_tag_id_by_name(
        session: Session,
        user_id: int,
        name: str,
    ) -> int | None:
        return session.scalar(
            select(Tag.id).where(
                Tag.user_id == user_id,
                Tag.name == name,
            )
        )
