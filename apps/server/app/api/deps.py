from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.client import OpenAICompatibleClient
from app.ai.service import AIService
from app.agent.article_content import ArticleContentService
from app.agent.chat import AgentChatService
from app.agent.context import AgentContext
from app.agent.fulltext import FullTextEvidenceSelector
from app.agent.graph import agent_graph
from app.agent.knowledge_search import KnowledgeSearchService
from app.agent.reasoning import AgentReasoningService
from app.agent.web_page_fetch import WebPageFetchService
from app.agent.web_search import TavilyWebSearchProvider, WebSearchService
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


def get_agent_chat_service() -> AgentChatService:
    """构建复用全局 InMemory checkpoint Graph 的 Chat Service。"""

    return AgentChatService(agent_graph)


def get_web_search_service() -> WebSearchService:
    """根据本机配置构建可替换 Provider 的只读 Web Search Service。"""

    return WebSearchService(
        TavilyWebSearchProvider(
            base_url=settings.web_search_base_url,
            api_key=settings.web_search_api_key,
            timeout_seconds=settings.web_search_timeout_seconds,
        ),
        max_results=settings.web_search_max_results,
    )


def get_article_content_service(
    session: Session,
    user_id: int,
) -> ArticleContentService:
    """构建绑定当前用户与当前数据库会话的文章全文读取服务。"""

    return ArticleContentService(session=session, user_id=user_id)


def get_web_page_fetch_service(
    crawler: CrawlerService | None = None,
) -> WebPageFetchService:
    """构建复用现有安全抓取主链的网页全文读取服务。"""

    return WebPageFetchService(crawler or get_crawler_service())


def get_fulltext_evidence_selector() -> FullTextEvidenceSelector:
    """构建共享单一上下文预算的临时全文证据选择器。"""

    return FullTextEvidenceSelector(
        chunker=TokenChunker(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        ),
        max_context_tokens=settings.agent_max_fulltext_context_tokens,
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


def get_agent_context(
    session: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    web_search_service: WebSearchService = Depends(get_web_search_service),
    crawler_service: CrawlerService = Depends(get_crawler_service),
) -> AgentContext:
    """构建绑定当前服务端用户的单次 Agent Runtime Context。"""

    llm_client = OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return AgentContext(
        knowledge_search=KnowledgeSearchService(
            session=session,
            user_id=user_id,
            embedding_service=embedding_service,
            similarity_threshold=settings.rag_similarity_threshold,
        ),
        web_search=web_search_service,
        reasoning=AgentReasoningService(llm_client),
        article_content=get_article_content_service(session, user_id),
        web_page_fetch=get_web_page_fetch_service(crawler_service),
        fulltext_selector=get_fulltext_evidence_selector(),
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
