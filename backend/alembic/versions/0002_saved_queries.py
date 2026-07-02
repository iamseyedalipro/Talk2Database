"""saved queries (the Questions library)

Adds the ``saved_queries`` table: a user-owned bookmark of a vetted query that
can be re-run without re-asking the AI. ``shared`` makes it visible to all users.

Revision ID: 0002_saved_queries
Revises: 0001_initial
Create Date: 2026-06-30 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0002_saved_queries"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0001 builds the panel schema via ``Base.metadata.create_all``, which now
    # also creates this table on a fresh database. Guard so this migration is a
    # no-op there yet still adds the table to databases initialized before it.
    bind = op.get_bind()
    if inspect(bind).has_table("saved_queries"):
        return

    op.create_table(
        "saved_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id",
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
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_saved_queries_owner_created", "saved_queries", ["owner_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("saved_queries"):
        return
    op.drop_index("ix_saved_queries_owner_created", table_name="saved_queries")
    op.drop_table("saved_queries")
