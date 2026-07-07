"""dashboards

Adds the dashboard tables (``dashboards``, ``dashboard_widgets``).

Guarded with ``has_table`` because 0001 creates every registered model via
``Base.metadata.create_all`` — on a fresh database these tables already exist
by the time this revision runs.

Revision ID: 0009_dashboards
Revises: 0008_chat_sessions
Create Date: 2026-07-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_dashboards"
down_revision: str | None = "0008_chat_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("dashboards"):
        op.create_table(
            "dashboards",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("shared", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_dashboards_owner_created", "dashboards", ["owner_id", "created_at"])

    if not inspector.has_table("dashboard_widgets"):
        op.create_table(
            "dashboard_widgets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "dashboard_id",
                sa.Integer(),
                sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("connections.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("sql", sa.Text(), nullable=False),
            sa.Column("viz_json", sa.JSON(), nullable=False),
            sa.Column("pos_x", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pos_y", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("width", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("height", sa.Integer(), nullable=False, server_default="4"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("dashboard_widgets"):
        op.drop_table("dashboard_widgets")
    if inspector.has_table("dashboards"):
        op.drop_table("dashboards")
