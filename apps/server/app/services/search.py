from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.article import Article


LIKE_ESCAPE = "\\"


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
