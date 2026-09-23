from typing import Protocol

from sqlalchemy.orm import Session

from app.agent.schemas import KnowledgeSearchInput, KnowledgeSearchResult
from app.services.search import QueryEmbeddingService, SearchService


class KnowledgeSearchProvider(Protocol):
    """供 Agent 编排层调用的知识库检索边界。"""

    def search(
        self,
        payload: KnowledgeSearchInput,
    ) -> list[KnowledgeSearchResult]: ...


class KnowledgeSearchService:
    """将现有 Semantic Search 转换为 Agent 所需的候选证据。"""

    def __init__(
        self,
        *,
        session: Session,
        user_id: int,
        embedding_service: QueryEmbeddingService,
        similarity_threshold: float,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._embedding_service = embedding_service
        self._similarity_threshold = similarity_threshold

    def search(
        self,
        payload: KnowledgeSearchInput,
    ) -> list[KnowledgeSearchResult]:
        hits = SearchService.semantic_search(
            self._session,
            self._user_id,
            payload.query,
            top_k=payload.top_k,
            similarity_threshold=self._similarity_threshold,
            embedding_service=self._embedding_service,
        )
        return [KnowledgeSearchResult.model_validate(hit) for hit in hits]
