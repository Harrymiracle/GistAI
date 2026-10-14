"""为标签增加正式主题和待整理状态。

Revision ID: b71c2d0e9f42
Revises: ad5ad692fa18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b71c2d0e9f42"
down_revision: str | Sequence[str] | None = "ad5ad692fa18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增状态列和合法值约束，既有标签使用默认正式状态。"""

    op.add_column(
        "tags",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_tags_status", "tags", "status IN ('active', 'pending')"
    )


def downgrade() -> None:
    """仅移除状态约束和状态列。"""

    op.drop_constraint("ck_tags_status", "tags", type_="check")
    op.drop_column("tags", "status")
