from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ai_service,
    get_crawler_service,
    get_current_user_id,
    get_db,
    get_min_content_chars,
)
from app.ai.service import AIService
from app.crawler.service import CrawlerService
from app.schemas.article import (
    ArticleCreate,
    ArticleDeleteResult,
    ArticleDetail,
    ArticleListData,
    ArticleListItem,
    ManualContentRequest,
    ArticleStatus,
    ArticleUpdate,
)
from app.schemas.common import ApiResponse
from app.services.article import ArticleService


router = APIRouter(prefix="/articles", tags=["articles"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
ArticleCrawler = Annotated[CrawlerService, Depends(get_crawler_service)]
ArticleAI = Annotated[AIService, Depends(get_ai_service)]
MinimumContentChars = Annotated[int, Depends(get_min_content_chars)]
ArticleProcessingStatus = Literal[
    "pending",
    "processing",
    "completed",
    "partial_failed",
    "failed",
]


@router.post(
    "",
    response_model=ApiResponse[ArticleDetail],
    status_code=status.HTTP_201_CREATED,
)
def create_article(
    payload: ArticleCreate,
    session: DatabaseSession,
    user_id: CurrentUserId,
    crawler: ArticleCrawler,
    ai_service: ArticleAI,
) -> ApiResponse[ArticleDetail]:
    """创建一篇待处理的 Article。"""

    article = ArticleService.create_and_process(
        session,
        payload,
        user_id,
        crawler,
        ai_service,
    )
    return ApiResponse(
        code=20100,
        message="Article 创建成功",
        data=ArticleDetail.model_validate(article),
    )


@router.post(
    "/{article_id}/manual-content",
    response_model=ApiResponse[ArticleDetail],
)
def set_manual_content(
    article_id: int,
    payload: ManualContentRequest,
    session: DatabaseSession,
    user_id: CurrentUserId,
    min_content_chars: MinimumContentChars,
    ai_service: ArticleAI,
) -> ApiResponse[ArticleDetail]:
    """使用清洗并校验后的手动正文恢复 Article 处理链路。"""

    article = ArticleService.set_manual_content_and_process(
        session,
        article_id,
        user_id,
        payload.content,
        min_content_chars,
        ai_service,
    )
    return ApiResponse(
        code=20000,
        message="手动正文保存成功",
        data=ArticleDetail.model_validate(article),
    )


@router.get("", response_model=ApiResponse[ArticleListData])
def list_articles(
    session: DatabaseSession,
    user_id: CurrentUserId,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    favorite: Annotated[bool | None, Query()] = None,
    status_filter: Annotated[
        ArticleProcessingStatus | None,
        Query(alias="status"),
    ] = None,
    source_type: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
) -> ApiResponse[ArticleListData]:
    """按创建时间倒序返回 Article 分页列表。"""

    articles, total = ArticleService.list_articles(
        session,
        user_id,
        page=page,
        page_size=page_size,
        favorite=favorite,
        status=status_filter,
        source_type=source_type,
    )
    data = ArticleListData(
        items=[ArticleListItem.model_validate(article) for article in articles],
        total=total,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(code=20000, message="Article 列表查询成功", data=data)


@router.get("/{article_id}/status", response_model=ApiResponse[ArticleStatus])
def get_article_status(
    article_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[ArticleStatus]:
    """返回 Article 当前处理状态及错误信息。"""

    article = ArticleService.get_article(session, article_id, user_id)
    return ApiResponse(
        code=20000,
        message="Article 状态查询成功",
        data=ArticleStatus.model_validate(article),
    )


@router.get("/{article_id}", response_model=ApiResponse[ArticleDetail])
def get_article(
    article_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[ArticleDetail]:
    """返回 Article 完整详情。"""

    article = ArticleService.get_article(session, article_id, user_id)
    return ApiResponse(
        code=20000,
        message="Article 查询成功",
        data=ArticleDetail.model_validate(article),
    )


@router.patch("/{article_id}", response_model=ApiResponse[ArticleDetail])
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[ArticleDetail]:
    """修改允许用户编辑的 Article 字段。"""

    article = ArticleService.update_article(session, article_id, user_id, payload)
    return ApiResponse(
        code=20000,
        message="Article 更新成功",
        data=ArticleDetail.model_validate(article),
    )


@router.delete("/{article_id}", response_model=ApiResponse[ArticleDeleteResult])
def delete_article(
    article_id: int,
    session: DatabaseSession,
    user_id: CurrentUserId,
) -> ApiResponse[ArticleDeleteResult]:
    """删除 Article，关联数据由数据库外键级联清理。"""

    deleted_id = ArticleService.delete_article(session, article_id, user_id)
    return ApiResponse(
        code=20000,
        message="Article 删除成功",
        data=ArticleDeleteResult(article_id=deleted_id),
    )
