"""create encrypted financial profile storage

Revision ID: 20260813_01
Revises:
Create Date: 2026-08-13 13:52:00+09:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_profiles",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("encrypted_profile", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
    )


def downgrade() -> None:
    op.drop_table("financial_profiles")
