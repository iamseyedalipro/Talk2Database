"""per-call LLM token usage records

Adds the ``token_usage`` table: one row per provider API call, aggregated by the
admin usage-monitoring endpoint into totals, per-user/model/provider breakdowns,
and a daily series.

``0001_initial`` builds the panel schema via ``Base.metadata.create_all``, so a
fresh database already has this table when the migration runs; the guard makes
it a no-op there and adds the table to databases initialized before it.

Revision ID: 0006_token_usage
Revises: 0005_connection_access
Create Date: 2026-07-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0006_token_usage"
down_revision: str | None = "0005_connection_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("token_usage"):
        return

    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_token_usage_created", "token_usage", ["created_at"])
    op.create_index("ix_token_usage_user_created", "token_usage", ["user_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("token_usage"):
        return
    op.drop_index("ix_token_usage_user_created", table_name="token_usage")
    op.drop_index("ix_token_usage_created", table_name="token_usage")
    op.drop_table("token_usage")
