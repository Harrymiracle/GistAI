from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Article(Base):
    """文章主表。"""

    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("user_id", "source_url", name="uq_articles_user_source_url"),
        Index("ix_articles_user_created_at", "user_id", "created_at"),
        Index("ix_articles_user_favorite", "user_id", "favorite"),
        Index("ix_articles_user_source_type", "user_id", "source_type"),
        Index("ix_articles_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255))

    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    clean_content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(CHAR(64))

    one_sentence_summary: Mapped[str | None] = mapped_column(Text)
    detailed_summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list[str] | None] = mapped_column(JSONB)

    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    fetch_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    ai_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    embedding_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )

    fetch_error: Mapped[str | None] = mapped_column(Text)
    ai_error: Mapped[str | None] = mapped_column(Text)
    embedding_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
