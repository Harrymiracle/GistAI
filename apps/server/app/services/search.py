from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import SemanticSearchEmbeddingError
from app.embedding.client import VECTOR_DIMENSION
from app.embedding.errors import EmbeddingError, EmbeddingResponseError
from app.models.article import Article
from app.models.article_chunk import ArticleChunk


LIKE_ESCAPE = "\\"


class QueryEmbeddingService(Protocol):
    def embed_query(self, query: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class SemanticSearchHit:
    article_id: int
    title: str | None
    chunk_id: int
    chunk_index: int
    excerpt: str
    score: float
    one_sentence_summary: str | None
    source_url: str
    source_name: str | None


class SearchService:
    """当前用户的 PostgreSQL 关键词搜索业务。"""

    @classmethod
    def keyword_search(
        cls,
        session: Session,
        user_id: int,
        keyword: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Article], int]:
        escaped_keyword = cls._escape_like(keyword)
        pattern = f"%{escaped_keyword}%"
        title_match = Article.title.ilike(pattern, escape=LIKE_ESCAPE)
        keyword_match = or_(
            title_match,
            Article.clean_content.ilike(pattern, escape=LIKE_ESCAPE),
            Article.one_sentence_summary.ilike(pattern, escape=LIKE_ESCAPE),
            Article.detailed_summary.ilike(pattern, escape=LIKE_ESCAPE),
        )
        filters = [Article.user_id == user_id, keyword_match]

        total = session.scalar(
            select(func.count()).select_from(Article).where(*filters)
        )
        statement: Select[tuple[Article]] = (
            select(Article)
            .where(*filters)
            .order_by(
                case((title_match, 0), else_=1),
                Article.created_at.desc(),
                Article.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(session.scalars(statement).all()), int(total or 0)

    @staticmethod
    def _escape_like(keyword: str) -> str:
        """将 LIKE 控制字符转换为字面量，避免意外通配。"""

        return (
            keyword.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
            .replace("%", f"{LIKE_ESCAPE}%")
            .replace("_", f"{LIKE_ESCAPE}_")
        )

    @staticmethod
    def semantic_search(
        session: Session,
        user_id: int,
        query: str,
        *,
        top_k: int,
        similarity_threshold: float,
        embedding_service: QueryEmbeddingService,
    ) -> list[SemanticSearchHit]:
        """生成 query vector，并按余弦相似度返回每篇文章的最佳切片。"""

        try:
            query_vector = embedding_service.embed_query(query)
            if len(query_vector) != VECTOR_DIMENSION:
                raise EmbeddingResponseError(
                    f"Embedding 向量维度必须为 {VECTOR_DIMENSION}"
                )
        except EmbeddingError as exc:
            raise SemanticSearchEmbeddingError(str(exc)) from exc

        distance = ArticleChunk.embedding.cosine_distance(query_vector)
        article_rank = func.row_number().over(
            partition_by=ArticleChunk.article_id,
            order_by=(
                distance.asc(),
                ArticleChunk.chunk_index.asc(),
                ArticleChunk.id.asc(),
            ),
        )
        ranked = (
            select(
                Article.id.label("article_id"),
                Article.title.label("title"),
                ArticleChunk.id.label("chunk_id"),
                ArticleChunk.chunk_index.label("chunk_index"),
                ArticleChunk.content.label("excerpt"),
                distance.label("distance"),
                Article.one_sentence_summary.label("one_sentence_summary"),
                Article.source_url.label("source_url"),
                Article.source_name.label("source_name"),
                article_rank.label("article_rank"),
            )
            .join(Article, Article.id == ArticleChunk.article_id)
            .where(
                Article.user_id == user_id,
                Article.embedding_status == "completed",
                ArticleChunk.embedding.is_not(None),
                distance <= 1.0 - similarity_threshold,
            )
            .subquery()
        )
        rows = session.execute(
            select(ranked)
            .where(ranked.c.article_rank == 1)
            .order_by(
                ranked.c.distance.asc(),
                ranked.c.article_id.asc(),
                ranked.c.chunk_index.asc(),
                ranked.c.chunk_id.asc(),
            )
            .limit(top_k)
        ).mappings()

        return [
            SemanticSearchHit(
                article_id=row["article_id"],
                title=row["title"],
                chunk_id=row["chunk_id"],
                chunk_index=row["chunk_index"],
                excerpt=row["excerpt"],
                score=1.0 - float(row["distance"]),
                one_sentence_summary=row["one_sentence_summary"],
                source_url=row["source_url"],
                source_name=row["source_name"],
            )
            for row in rows
        ]
