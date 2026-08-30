"""create core tables

Revision ID: ad5ad692fa18
Revises: 
Create Date: 2026-08-30 10:38:21.018980
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'ad5ad692fa18'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """执行升级。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('articles',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('source_name', sa.String(length=255), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('author', sa.String(length=255), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clean_content', sa.Text(), nullable=True),
    sa.Column('content_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('one_sentence_summary', sa.Text(), nullable=True),
    sa.Column('detailed_summary', sa.Text(), nullable=True),
    sa.Column('key_points', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('favorite', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('fetch_status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('ai_status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('embedding_status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('fetch_error', sa.Text(), nullable=True),
    sa.Column('ai_error', sa.Text(), nullable=True),
    sa.Column('embedding_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'source_url', name='uq_articles_user_source_url')
    )
    op.create_index('ix_articles_user_created_at', 'articles', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_articles_user_favorite', 'articles', ['user_id', 'favorite'], unique=False)
    op.create_index('ix_articles_user_source_type', 'articles', ['user_id', 'source_type'], unique=False)
    op.create_index('ix_articles_user_status', 'articles', ['user_id', 'status'], unique=False)
    op.create_table('tags',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='uq_tags_user_name')
    )
    op.create_table('article_chunks',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('article_id', sa.BigInteger(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=True),
    sa.Column('embedding', Vector(1024), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('article_id', 'chunk_index', name='uq_article_chunks_article_index')
    )
    op.create_table('article_tags',
    sa.Column('article_id', sa.BigInteger(), nullable=False),
    sa.Column('tag_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('article_id', 'tag_id')
    )
    op.create_index('ix_article_tags_tag_id', 'article_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    """执行回滚。"""
    op.drop_index('ix_article_tags_tag_id', table_name='article_tags')
    op.drop_table('article_tags')
    op.drop_table('article_chunks')
    op.drop_table('tags')
    op.drop_index('ix_articles_user_status', table_name='articles')
    op.drop_index('ix_articles_user_source_type', table_name='articles')
    op.drop_index('ix_articles_user_favorite', table_name='articles')
    op.drop_index('ix_articles_user_created_at', table_name='articles')
    op.drop_table('articles')
    op.execute("DROP EXTENSION IF EXISTS vector")
