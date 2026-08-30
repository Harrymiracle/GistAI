from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db, get_embedding_service
from app.core.config import settings
from app.embedding.service import EmbeddingService
from app.schemas.common import ApiResponse
from app.schemas.search import (
    KeywordSearchData,
    KeywordSearchItem,
    KeywordSearchParams,
    SemanticSearchData,
    SemanticSearchItem,
    SemanticSearchRequest,
)
from app.services.search import SearchService


router = APIRouter(prefix="/search", tags=["search"])

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
KeywordQuery = Annotated[KeywordSearchParams, Query()]
EmbeddingDependency = Annotated[EmbeddingService, Depends(get_embedding_service)]


@router.get("/keyword", response_model=ApiResponse[KeywordSearchData])
def keyword_search(
    params: KeywordQuery,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[KeywordSearchData]:
    articles, total = SearchService.keyword_search(
        session,
        user_id,
        params.q,
        page=params.page,
        page_size=params.page_size,
    )
    data = KeywordSearchData(
        items=[KeywordSearchItem.model_validate(article) for article in articles],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
    return ApiResponse(code=20000, message="关键词搜索成功", data=data)


@router.post("/semantic", response_model=ApiResponse[SemanticSearchData])
def semantic_search(
    payload: SemanticSearchRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    embedding_service: EmbeddingDependency,
) -> ApiResponse[SemanticSearchData]:
    hits = SearchService.semantic_search(
        session,
        user_id,
        payload.query,
        top_k=payload.top_k,
        similarity_threshold=settings.rag_similarity_threshold,
        embedding_service=embedding_service,
    )
    data = SemanticSearchData(
        items=[SemanticSearchItem.model_validate(hit) for hit in hits],
        top_k=payload.top_k,
        similarity_threshold=settings.rag_similarity_threshold,
    )
    return ApiResponse(code=20000, message="语义搜索成功", data=data)
