"""semantic layer (glossary descriptions + metrics)

Adds per-connection annotations fed into the AI prompt: ``glossary_descriptions``
(table/column meanings; a blank ``column_name`` is table-level) and ``metrics``
(named business definitions like "MRR" or "active user").

Revision ID: 0003_glossary
Revises: 0002_saved_queries
Create Date: 2026-06-30 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0003_glossary"
down_revision: str | None = "0002_saved_queries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # See 0002: 0001's ``create_all`` already builds these on a fresh database,
    # so only create them where they are missing (databases initialized earlier).
    inspector = inspect(op.get_bind())

    if not inspector.has_table("glossary_descriptions"):
        op.create_table(
            "glossary_descriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("column_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "connection_id", "table_name", "column_name", name="uq_glossary_target"
            ),
        )

    if not inspector.has_table("metrics"):
        op.create_table(
            "metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("expression", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("connection_id", "name", name="uq_metric_name"),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("metrics"):
        op.drop_table("metrics")
    if inspector.has_table("glossary_descriptions"):
        op.drop_table("glossary_descriptions")
