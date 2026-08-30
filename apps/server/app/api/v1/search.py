from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.schemas.common import ApiResponse
from app.schemas.search import (
    KeywordSearchData,
    KeywordSearchItem,
    KeywordSearchParams,
)
from app.services.search import SearchService


router = APIRouter(prefix="/search", tags=["search"])

DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
KeywordQuery = Annotated[KeywordSearchParams, Query()]


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
