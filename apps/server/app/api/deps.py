from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.client import OpenAICompatibleClient
from app.ai.service import AIService
from app.core.config import settings
from app.crawler.browser_fetcher import PlaywrightFetcher
from app.crawler.extractor import ArticleExtractor
from app.crawler.http_fetcher import HttpFetcher
from app.crawler.service import CrawlerService
from app.db.session import SessionLocal
from app.embedding.chunker import TokenChunker
from app.embedding.client import OpenAICompatibleEmbeddingClient
from app.embedding.service import EmbeddingService
from app.rag.service import RAGService


DEFAULT_USER_ID = 1


def get_db() -> Generator[Session, None, None]:
    """为单次请求提供数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id() -> int:
    """返回 V1 默认用户，后续可替换为认证结果。"""

    return DEFAULT_USER_ID


def get_crawler_service() -> CrawlerService:
    """按当前配置构建普通网页抓取服务。"""

    return CrawlerService(
        fetcher=HttpFetcher(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_redirects=settings.fetch_max_redirects,
            user_agent=settings.fetch_user_agent,
        ),
        extractor=ArticleExtractor(
            min_content_chars=settings.fetch_min_content_chars,
        ),
        browser_fetcher=PlaywrightFetcher(
            navigation_timeout_seconds=settings.playwright_navigation_timeout_seconds,
            network_idle_timeout_seconds=settings.playwright_network_idle_timeout_seconds,
            user_agent=settings.fetch_user_agent,
        ),
    )


def get_min_content_chars() -> int:
    """返回网页提取和手动正文共用的最小正文长度。"""

    return settings.fetch_min_content_chars


def get_ai_service() -> AIService:
    """根据本机环境变量构建 OpenAI-compatible AI Service。"""

    return AIService(
        OpenAICompatibleClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )


def get_embedding_service() -> EmbeddingService:
    """根据本机配置构建 token 切片与 OpenAI-compatible Embedding Service。"""

    return EmbeddingService(
        chunker=TokenChunker(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        ),
        client=OpenAICompatibleEmbeddingClient(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            timeout_seconds=settings.embedding_timeout_seconds,
        ),
        batch_size=settings.embedding_batch_size,
    )


def get_rag_service(
    ai_service: AIService = Depends(get_ai_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> RAGService:
    """构建复用现有 AI 与 Embedding 能力的单轮 RAG Service。"""

    return RAGService(
        embedding_service=embedding_service,
        ai_service=ai_service,
        similarity_threshold=settings.rag_similarity_threshold,
        max_context_chars=settings.rag_max_context_chars,
    )
