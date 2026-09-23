import hashlib
import logging

from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.errors import AIError
from app.ai.schemas import AIArticleResult
from app.ai.service import ArticleAIProcessor
from app.core.exceptions import (
    ArticleAlreadyExistsError,
    ArticleContentUnavailableError,
    ArticleNotFoundError,
    ArticleProcessingConflictError,
    ArticleSourceUrlInvalidError,
    ManualContentInvalidError,
)
from app.crawler.cleaner import ContentValidationError, clean_and_validate_content
from app.crawler.errors import CrawlerError
from app.crawler.extractor import ExtractedArticle
from app.crawler.service import CrawlerService
from app.embedding.errors import EmbeddingError
from app.embedding.schemas import EmbeddedChunk
from app.embedding.service import ArticleEmbeddingProcessor
from app.models.article import Article
from app.models.article_chunk import ArticleChunk
from app.models.article_tag import ArticleTag
from app.models.tag import Tag
from app.schemas.article import ArticleCreate, ArticleUpdate


PENDING_STATUS = "pending"
PROCESSING_STATUS = "processing"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
PARTIAL_FAILED_STATUS = "partial_failed"
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
            article.content_hash = cls._content_hash(extracted.clean_content)
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
    def create_and_process(
        cls,
        session: Session,
        payload: ArticleCreate,
        user_id: int,
        crawler: CrawlerService,
        ai_service: ArticleAIProcessor,
        embedding_service: ArticleEmbeddingProcessor,
    ) -> Article:
        """同步执行创建、正文获取、AI 分析和 Embedding 主链路。"""

        article = cls.create_and_fetch(session, payload, user_id, crawler)
        article = cls.process_ai_if_ready(session, article, ai_service)
        return cls.process_embedding_if_ready(session, article, embedding_service)

    @classmethod
    def set_manual_content(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        content: str,
        min_content_chars: int,
    ) -> Article:
        """校验完成后原子替换正文，并恢复抓取阶段成功状态。"""

        article = cls.get_article(session, article_id, user_id)
        try:
            clean_content = clean_and_validate_content(
                content,
                min_content_chars,
                content_label="手动正文",
            )
        except ContentValidationError as exc:
            raise ManualContentInvalidError(str(exc)) from exc

        content_hash = cls._content_hash(clean_content)
        article.clean_content = clean_content
        article.content_hash = content_hash
        article.status = PROCESSING_STATUS
        article.fetch_status = COMPLETED_STATUS
        article.fetch_error = None
        article.ai_status = PENDING_STATUS
        article.ai_error = None
        article.embedding_status = PENDING_STATUS
        article.embedding_error = None
        cls._commit(session)
        session.refresh(article)
        return article

    @classmethod
    def set_manual_content_and_process(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        content: str,
        min_content_chars: int,
        ai_service: ArticleAIProcessor,
        embedding_service: ArticleEmbeddingProcessor,
    ) -> Article:
        """保存手动正文后同步进入 AI 与 Embedding 分析。"""

        article = cls.set_manual_content(
            session,
            article_id,
            user_id,
            content,
            min_content_chars,
        )
        article = cls.process_ai_if_ready(session, article, ai_service)
        return cls.process_embedding_if_ready(session, article, embedding_service)

    @classmethod
    def process_ai_if_ready(
        cls,
        session: Session,
        article: Article,
        ai_service: ArticleAIProcessor,
    ) -> Article:
        """仅对已获得有效正文的 Article 执行 AI，并安全持久化状态。"""

        if article.fetch_status != COMPLETED_STATUS or not article.clean_content:
            return article

        article.status = PROCESSING_STATUS
        article.ai_status = PROCESSING_STATUS
        article.ai_error = None
        cls._commit(session)

        try:
            result = ai_service.generate_article_result(article.clean_content)
        except AIError as exc:
            cls._mark_ai_failed(session, article, str(exc))
        except Exception:
            logger.exception("Article %s AI 处理发生未预期异常", article.id)
            cls._mark_ai_failed(session, article, "AI 处理失败")
        else:
            cls._apply_ai_result(session, article, result)

        session.refresh(article)
        return article

    @classmethod
    def _apply_ai_result(
        cls,
        session: Session,
        article: Article,
        result: AIArticleResult,
    ) -> None:
        article.one_sentence_summary = result.one_sentence_summary
        article.key_points = result.key_points
        article.detailed_summary = result.detailed_summary
        article.ai_status = COMPLETED_STATUS
        article.ai_error = None
        article.embedding_status = PENDING_STATUS
        article.embedding_error = None
        article.status = PROCESSING_STATUS
        cls._replace_ai_tags(session, article, result.tags)
        cls._commit(session)
        session.expire(article, ["tags"])

    @classmethod
    def _mark_ai_failed(
        cls,
        session: Session,
        article: Article,
        error_message: str,
    ) -> None:
        article.status = PARTIAL_FAILED_STATUS
        article.ai_status = FAILED_STATUS
        article.ai_error = error_message
        article.embedding_status = PENDING_STATUS
        cls._commit(session)

    @classmethod
    def process_embedding_if_ready(
        cls,
        session: Session,
        article: Article,
        embedding_service: ArticleEmbeddingProcessor,
    ) -> Article:
        """仅在正文与 AI 均完成后生成切片和向量。"""

        if (
            article.fetch_status != COMPLETED_STATUS
            or article.ai_status != COMPLETED_STATUS
            or not article.clean_content
        ):
            return article

        article.status = PROCESSING_STATUS
        article.embedding_status = PROCESSING_STATUS
        article.embedding_error = None
        cls._commit(session)

        try:
            chunks = embedding_service.generate(article.clean_content)
            if not chunks:
                raise EmbeddingError("正文未生成有效切片")
        except EmbeddingError as exc:
            cls._mark_embedding_failed(session, article, str(exc))
        except Exception:
            logger.error("Article %s Embedding 处理发生未预期异常", article.id)
            cls._mark_embedding_failed(session, article, "Embedding 处理失败")
        else:
            try:
                cls._apply_embedding_result(session, article, chunks)
            except SQLAlchemyError:
                logger.error("Article %s Embedding 数据保存失败", article.id)
                cls._mark_embedding_failed(session, article, "Embedding 数据保存失败")

        session.refresh(article)
        return article

    @classmethod
    def reprocess(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        crawler: CrawlerService,
        ai_service: ArticleAIProcessor,
        embedding_service: ArticleEmbeddingProcessor,
    ) -> tuple[Article, bool]:
        """在完整新 Pipeline 准备成功后原子替换旧有效数据。"""

        article = cls._get_article_for_update(session, article_id, user_id)
        cls._ensure_not_processing(article)
        cls._validate_reprocessable_url(article.source_url)
        previous_ai_status = article.ai_status
        previous_ai_error = article.ai_error
        article.status = PROCESSING_STATUS
        article.fetch_status = PROCESSING_STATUS
        article.fetch_error = None
        cls._commit(session)

        try:
            extracted = crawler.fetch_article(article.source_url)
        except CrawlerError as exc:
            cls._finish_reprocess_fetch_failure(session, article, str(exc))
            return cls._refresh(session, article), False
        except Exception:
            logger.exception("Article %s 重新抓取发生未预期异常", article.id)
            cls._finish_reprocess_fetch_failure(session, article, "网页重新抓取处理失败")
            return cls._refresh(session, article), False

        new_hash = cls._content_hash(extracted.clean_content)
        if new_hash == article.content_hash:
            article.fetch_status = COMPLETED_STATUS
            article.fetch_error = None
            article.status = cls._calculate_overall_status(article)
            cls._commit(session)
            return cls._refresh(session, article), True

        article.fetch_status = COMPLETED_STATUS
        article.fetch_error = None
        article.ai_status = PROCESSING_STATUS
        article.ai_error = None
        article.status = PROCESSING_STATUS
        cls._commit(session)

        try:
            ai_result = ai_service.generate_article_result(extracted.clean_content)
        except AIError as exc:
            cls._finish_reprocess_ai_failure(session, article, str(exc))
            return cls._refresh(session, article), False
        except Exception:
            logger.exception("Article %s 重处理 AI 发生未预期异常", article.id)
            cls._finish_reprocess_ai_failure(session, article, "AI 重新处理失败")
            return cls._refresh(session, article), False

        article.ai_status = COMPLETED_STATUS
        article.ai_error = None
        article.embedding_status = PROCESSING_STATUS
        article.embedding_error = None
        article.status = PROCESSING_STATUS
        cls._commit(session)

        try:
            chunks = embedding_service.generate(extracted.clean_content)
            if not chunks:
                raise EmbeddingError("正文未生成有效切片")
        except EmbeddingError as exc:
            cls._finish_reprocess_embedding_failure(
                session,
                article,
                str(exc),
                previous_ai_status,
                previous_ai_error,
            )
            return cls._refresh(session, article), False
        except Exception:
            logger.exception("Article %s 重处理 Embedding 发生未预期异常", article.id)
            cls._finish_reprocess_embedding_failure(
                session,
                article,
                "Embedding 重新处理失败",
                previous_ai_status,
                previous_ai_error,
            )
            return cls._refresh(session, article), False

        try:
            cls._apply_complete_reprocess(
                session,
                article,
                extracted,
                new_hash,
                ai_result,
                chunks,
            )
        except SQLAlchemyError:
            logger.exception("Article %s 重处理结果保存失败", article.id)
            session.refresh(article)
            cls._finish_reprocess_embedding_failure(
                session,
                article,
                "重处理结果保存失败",
                previous_ai_status,
                previous_ai_error,
            )
        return cls._refresh(session, article), False

    @classmethod
    def regenerate_ai(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        min_content_chars: int,
        ai_service: ArticleAIProcessor,
    ) -> Article:
        """基于当前正文原子替换 AI 字段与标签，不触碰 Embedding。"""

        article = cls._get_article_for_update(session, article_id, user_id)
        cls._ensure_not_processing(article)
        clean_content = cls._require_valid_saved_content(article, min_content_chars)
        article.status = PROCESSING_STATUS
        article.ai_status = PROCESSING_STATUS
        article.ai_error = None
        cls._commit(session)

        try:
            result = ai_service.generate_article_result(clean_content)
        except AIError as exc:
            cls._finish_regenerated_ai_failure(session, article, str(exc))
        except Exception:
            logger.exception("Article %s 重新生成 AI 发生未预期异常", article.id)
            cls._finish_regenerated_ai_failure(session, article, "AI 重新生成失败")
        else:
            try:
                cls._apply_regenerated_ai(session, article, result)
            except SQLAlchemyError:
                logger.exception("Article %s 重新生成 AI 数据保存失败", article.id)
                session.refresh(article)
                cls._finish_regenerated_ai_failure(
                    session, article, "AI 重新生成结果保存失败"
                )
        return cls._refresh(session, article)

    @classmethod
    def regenerate_embedding(
        cls,
        session: Session,
        article_id: int,
        user_id: int,
        min_content_chars: int,
        embedding_service: ArticleEmbeddingProcessor,
    ) -> Article:
        """基于当前正文原子替换 chunks/vectors，不触碰抓取和 AI 数据。"""

        article = cls._get_article_for_update(session, article_id, user_id)
        cls._ensure_not_processing(article)
        clean_content = cls._require_valid_saved_content(article, min_content_chars)
        article.status = PROCESSING_STATUS
        article.embedding_status = PROCESSING_STATUS
        article.embedding_error = None
        cls._commit(session)

        try:
            chunks = embedding_service.generate(clean_content)
            if not chunks:
                raise EmbeddingError("正文未生成有效切片")
        except EmbeddingError as exc:
            cls._finish_regenerated_embedding_failure(session, article, str(exc))
        except Exception:
            logger.exception("Article %s 重新生成 Embedding 发生未预期异常", article.id)
            cls._finish_regenerated_embedding_failure(
                session, article, "Embedding 重新生成失败"
            )
        else:
            try:
                cls._apply_embedding_result(session, article, chunks)
            except SQLAlchemyError:
                logger.exception("Article %s Embedding 数据保存失败", article.id)
                session.refresh(article)
                cls._finish_regenerated_embedding_failure(
                    session, article, "Embedding 重新生成结果保存失败"
                )
        return cls._refresh(session, article)

    @classmethod
    def _apply_embedding_result(
        cls,
        session: Session,
        article: Article,
        chunks: list[EmbeddedChunk],
    ) -> None:
        session.execute(
            delete(ArticleChunk).where(ArticleChunk.article_id == article.id)
        )
        session.add_all(
            [
                ArticleChunk(
                    article_id=article.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                    chunk_metadata=chunk.metadata,
                )
                for chunk in chunks
            ]
        )
        article.embedding_status = COMPLETED_STATUS
        article.embedding_error = None
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @classmethod
    def _mark_embedding_failed(
        cls,
        session: Session,
        article: Article,
        error_message: str,
    ) -> None:
        article.embedding_status = FAILED_STATUS
        article.embedding_error = error_message
        article.status = PARTIAL_FAILED_STATUS
        cls._commit(session)

    @classmethod
    def _apply_regenerated_ai(
        cls,
        session: Session,
        article: Article,
        result: AIArticleResult,
    ) -> None:
        article.one_sentence_summary = result.one_sentence_summary
        article.key_points = result.key_points
        article.detailed_summary = result.detailed_summary
        article.ai_status = COMPLETED_STATUS
        article.ai_error = None
        cls._replace_ai_tags(session, article, result.tags)
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)
        session.expire(article, ["tags"])

    @classmethod
    def _apply_complete_reprocess(
        cls,
        session: Session,
        article: Article,
        extracted: ExtractedArticle,
        new_hash: str,
        ai_result: AIArticleResult,
        chunks: list[EmbeddedChunk],
    ) -> None:
        article.clean_content = extracted.clean_content
        article.content_hash = new_hash
        if article.title is None:
            article.title = extracted.title
        if article.author is None:
            article.author = extracted.author
        if article.published_at is None:
            article.published_at = extracted.published_at
        if article.source_name is None:
            article.source_name = extracted.source_name
        article.one_sentence_summary = ai_result.one_sentence_summary
        article.key_points = ai_result.key_points
        article.detailed_summary = ai_result.detailed_summary
        cls._replace_ai_tags(session, article, ai_result.tags)
        session.execute(delete(ArticleChunk).where(ArticleChunk.article_id == article.id))
        session.add_all(
            [
                ArticleChunk(
                    article_id=article.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                    chunk_metadata=chunk.metadata,
                )
                for chunk in chunks
            ]
        )
        article.fetch_status = COMPLETED_STATUS
        article.fetch_error = None
        article.ai_status = COMPLETED_STATUS
        article.ai_error = None
        article.embedding_status = COMPLETED_STATUS
        article.embedding_error = None
        article.status = COMPLETED_STATUS
        cls._commit(session)
        session.expire(article, ["tags"])

    @classmethod
    def _finish_reprocess_fetch_failure(
        cls, session: Session, article: Article, message: str
    ) -> None:
        article.fetch_status = FAILED_STATUS
        article.fetch_error = message
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @classmethod
    def _finish_reprocess_ai_failure(
        cls, session: Session, article: Article, message: str
    ) -> None:
        article.ai_status = FAILED_STATUS
        article.ai_error = message
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @classmethod
    def _finish_reprocess_embedding_failure(
        cls,
        session: Session,
        article: Article,
        message: str,
        previous_ai_status: str,
        previous_ai_error: str | None,
    ) -> None:
        article.ai_status = previous_ai_status
        article.ai_error = previous_ai_error
        article.embedding_status = FAILED_STATUS
        article.embedding_error = message
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @classmethod
    def _finish_regenerated_ai_failure(
        cls, session: Session, article: Article, message: str
    ) -> None:
        article.ai_status = FAILED_STATUS
        article.ai_error = message
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @classmethod
    def _finish_regenerated_embedding_failure(
        cls, session: Session, article: Article, message: str
    ) -> None:
        article.embedding_status = FAILED_STATUS
        article.embedding_error = message
        article.status = cls._calculate_overall_status(article)
        cls._commit(session)

    @staticmethod
    def _calculate_overall_status(article: Article) -> str:
        statuses = [article.fetch_status, article.ai_status, article.embedding_status]
        if PROCESSING_STATUS in statuses:
            return PROCESSING_STATUS
        if FAILED_STATUS in statuses:
            return PARTIAL_FAILED_STATUS if article.clean_content else FAILED_STATUS
        if all(status == COMPLETED_STATUS for status in statuses):
            return COMPLETED_STATUS
        if all(status == PENDING_STATUS for status in statuses):
            return PENDING_STATUS
        return PROCESSING_STATUS

    @staticmethod
    def _ensure_not_processing(article: Article) -> None:
        if article.status == PROCESSING_STATUS or PROCESSING_STATUS in (
            article.fetch_status,
            article.ai_status,
            article.embedding_status,
        ):
            raise ArticleProcessingConflictError()

    @staticmethod
    def _validate_reprocessable_url(source_url: str) -> None:
        try:
            TypeAdapter(HttpUrl).validate_python(source_url)
        except ValidationError as exc:
            raise ArticleSourceUrlInvalidError() from exc

    @staticmethod
    def _require_valid_saved_content(
        article: Article,
        min_content_chars: int,
    ) -> str:
        if not article.clean_content:
            raise ArticleContentUnavailableError()
        try:
            clean_and_validate_content(
                article.clean_content,
                min_content_chars,
                content_label="已保存正文",
            )
        except ContentValidationError as exc:
            raise ArticleContentUnavailableError(str(exc)) from exc
        return article.clean_content

    @staticmethod
    def _get_article_for_update(
        session: Session,
        article_id: int,
        user_id: int,
    ) -> Article:
        article = session.scalar(
            select(Article)
            .where(Article.id == article_id, Article.user_id == user_id)
            .with_for_update()
        )
        if article is None:
            raise ArticleNotFoundError()
        return article

    @staticmethod
    def _refresh(session: Session, article: Article) -> Article:
        session.refresh(article)
        return article

    @staticmethod
    def _replace_ai_tags(
        session: Session,
        article: Article,
        tag_names: list[str],
    ) -> None:
        existing_tags = session.scalars(
            select(Tag).where(
                Tag.user_id == article.user_id,
                Tag.name.in_(tag_names),
            )
        ).all()
        tags_by_name = {tag.name: tag for tag in existing_tags}

        session.execute(
            delete(ArticleTag).where(ArticleTag.article_id == article.id)
        )
        for tag_name in tag_names:
            tag = tags_by_name.get(tag_name)
            if tag is None:
                tag = Tag(user_id=article.user_id, name=tag_name)
                session.add(tag)
                session.flush()
                tags_by_name[tag_name] = tag
            session.add(ArticleTag(article_id=article.id, tag_id=tag.id))

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
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

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
