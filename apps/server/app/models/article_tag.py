from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArticleTag(Base):
    """文章与标签的关联表。"""

    __tablename__ = "article_tags"
    __table_args__ = (Index("ix_article_tags_tag_id", "tag_id"),)

    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
