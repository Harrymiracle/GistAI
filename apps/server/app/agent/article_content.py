from typing import Protocol

from sqlalchemy.orm import Session

from app.agent.schemas import ArticleContentResult
from app.core.exceptions import ArticleNotFoundError
from app.services.article import ArticleService


class ArticleContentProvider(Protocol):
    """供 Agent 读取当前用户文章正文的边界。"""

    def get(self, article_id: int) -> ArticleContentResult | None: ...


class ArticleContentService:
    """复用 ArticleService，并将不存在与越权统一为不可用。"""

    def __init__(self, *, session: Session, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    def get(self, article_id: int) -> ArticleContentResult | None:
        try:
            article = ArticleService.get_article(
                self._session,
                article_id,
                self._user_id,
            )
        except ArticleNotFoundError:
            return None
        if not article.clean_content or not article.clean_content.strip():
            return None
        return ArticleContentResult(
            article_id=article.id,
            title=article.title,
            clean_content=article.clean_content,
            url=article.source_url,
            author=article.author,
            published_at=article.published_at,
        )
