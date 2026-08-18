"""add fixed-window rate limit counters

Revision ID: 20260814_01
Revises: 20260813_02
Create Date: 2026-08-14 11:00:00+09:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_01"
down_revision: str | None = "20260813_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key", "window_start"),
    )
    op.create_index(
        "ix_rate_limit_counters_window_end",
        "rate_limit_counters",
        ["window_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_counters_window_end",
        table_name="rate_limit_counters",
    )
    op.drop_table("rate_limit_counters")
