"""add anonymous sessions and profile ownership

Revision ID: 20260813_02
Revises: 20260813_01
Create Date: 2026-08-13 14:30:00+09:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_02"
down_revision: str | None = "20260813_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_auth_sessions_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    with op.batch_alter_table("financial_profiles") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_financial_profiles_owner_user_id",
            "users",
            ["owner_user_id"],
            ["user_id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_financial_profiles_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("financial_profiles") as batch_op:
        batch_op.drop_index("ix_financial_profiles_owner_user_id")
        batch_op.drop_constraint(
            "fk_financial_profiles_owner_user_id",
            type_="foreignkey",
        )
        batch_op.drop_column("owner_user_id")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
