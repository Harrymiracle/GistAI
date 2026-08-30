import hashlib
import logging

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ArticleAlreadyExistsError, ArticleNotFoundError
from app.crawler.errors import CrawlerError
from app.crawler.service import CrawlerService
from app.models.article import Article
from app.schemas.article import ArticleCreate, ArticleUpdate


PENDING_STATUS = "pending"
PROCESSING_STATUS = "processing"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
logger = logging.getLogger(__name__)


class ArticleService:
    """Article 基础 CRUD 业务。"""

    @staticmethod
    def _create_pending_article(
        session: Session,
        payload: ArticleCreate,
        user_id: int,
    ) -> Article:
        source_url = str(payload.source_url)
        existing_id = session.scalar(
            select(Article.id).where(
                Article.user_id == user_id,
                Article.source_url == source_url,
            )
        )
        if existing_id is not None:
            raise ArticleAlreadyExistsError(existing_id)

        article = Article(
            user_id=user_id,
            source_url=source_url,
            source_type=payload.source_type,
            source_name=payload.source_name,
            title=payload.title,
            author=payload.author,
            published_at=payload.published_at,
            favorite=payload.favorite,
            status=PENDING_STATUS,
            fetch_status=PENDING_STATUS,
            ai_status=PENDING_STATUS,
            embedding_status=PENDING_STATUS,
        )
        session.add(article)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = session.scalar(
                select(Article.id).where(
                    Article.user_id == user_id,
                    Article.source_url == source_url,
                )
            )
            if existing_id is not None:
                raise ArticleAlreadyExistsError(existing_id) from None
            raise
        except SQLAlchemyError:
            session.rollback()
            raise

        session.refresh(article)
        return article

    @classmethod
    def create_and_fetch(
        cls,
        session: Session,
        payload: ArticleCreate,
        user_id: int,
        crawler: CrawlerService,
    ) -> Article:
        """先持久化 Article，再同步执行普通 HTTP 抓取。"""

        article = cls._create_pending_article(session, payload, user_id)
        article.status = PROCESSING_STATUS
        article.fetch_status = PROCESSING_STATUS
        article.fetch_error = None
        cls._commit(session)

        try:
            extracted = crawler.fetch_article(article.source_url)
        except CrawlerError as exc:
            cls._mark_fetch_failed(session, article, str(exc))
        except Exception:
            logger.exception("Article %s 抓取发生未预期异常", article.id)
            cls._mark_fetch_failed(session, article, "网页抓取处理失败")
        else:
            article.clean_content = extracted.clean_content
            article.content_hash = hashlib.sha256(
                extracted.clean_content.encode("utf-8")
            ).hexdigest()
            article.fetch_status = COMPLETED_STATUS
            article.fetch_error = None
            article.status = PROCESSING_STATUS
            if article.title is None:
                article.title = extracted.title
            if article.author is None:
                article.author = extracted.author
            if article.published_at is None:
                article.published_at = extracted.published_at
            if article.source_name is None:
                article.source_name = extracted.source_name
            cls._commit(session)

        session.refresh(article)
        return article

    @classmethod
    def _mark_fetch_failed(
        cls,
        session: Session,
        article: Article,
        error_message: str,
    ) -> None:
        article.status = FAILED_STATUS
        article.fetch_status = FAILED_STATUS
        article.fetch_error = error_message
        cls._commit(session)

    @staticmethod
    def list_articles(
        session: Session,
        user_id: int,
        *,
        page: int,
        page_size: int,
        favorite: bool | None,
        status: str | None,
        source_type: str | None,
    ) -> tuple[list[Article], int]:
        filters = [Article.user_id == user_id]
        if favorite is not None:
            filters.append(Article.favorite == favorite)
        if status is not None:
            filters.append(Article.status == status)
        if source_type is not None:
            filters.append(Article.source_type == source_type)

        total = session.scalar(
            select(func.count()).select_from(Article).where(*filters)
        )
        statement: Select[tuple[Article]] = (
            select(Article)
            .where(*filters)
            .order_by(Article.created_at.desc(), Article.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        articles = list(session.scalars(statement).all())
        return articles, int(total or 0)

    @staticmethod
    def get_article(session: Session, article_id: int, user_id: int) -> Article:
        article = session.scalar(
            select(Article).where(
                Article.id == article_id,
                Article.user_id == user_id,
            )
        )
        if article is None:
            raise ArticleNotFoundError()
        return article

    @classmethod
    def update_article(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        payload: ArticleUpdate,
    ) -> Article:
        article = cls.get_article(session, article_id, user_id)
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(article, field_name, value)

        cls._commit(session)
        session.refresh(article)
        return article

    @classmethod
    def delete_article(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
    ) -> int:
        article = cls.get_article(session, article_id, user_id)
        session.delete(article)
        cls._commit(session)
        return article_id

    @staticmethod
    def _commit(session: Session) -> None:
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
