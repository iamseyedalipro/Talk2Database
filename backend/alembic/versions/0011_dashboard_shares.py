"""dashboard shares (per-user view/edit sharing)

Adds the ``dashboard_shares`` join table: a dashboard owner can share a
dashboard they own with specific users at a ``view`` or ``edit`` access level.
This layers on top of the existing global ``dashboards.shared`` toggle.

``0001_initial`` builds the panel schema via ``Base.metadata.create_all``, so a
fresh database already has this table when the migration runs; the guard makes
it a no-op there and adds the table to databases initialized before it.

Revision ID: 0011_dashboard_shares
Revises: 0010_user_language
Create Date: 2026-07-08 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0011_dashboard_shares"
down_revision: str | None = "0010_user_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("dashboard_shares"):
        return

    # create_table creates the ``dashboard_access_level`` enum type as a side
    # effect of the column below (Postgres); downgrade drops it explicitly.
    op.create_table(
        "dashboard_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dashboard_id",
            sa.Integer(),
            sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_level",
            sa.Enum("view", "edit", name="dashboard_access_level"),
            nullable=False,
        ),
        sa.Column(
            "granted_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("dashboard_id", "user_id", name="uq_dashboard_share"),
    )
    op.create_index("ix_dashboard_shares_dashboard_id", "dashboard_shares", ["dashboard_id"])
    op.create_index("ix_dashboard_shares_user_id", "dashboard_shares", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("dashboard_shares"):
        return
    op.drop_index("ix_dashboard_shares_user_id", table_name="dashboard_shares")
    op.drop_index("ix_dashboard_shares_dashboard_id", table_name="dashboard_shares")
    op.drop_table("dashboard_shares")
    sa.Enum(name="dashboard_access_level").drop(bind, checkfirst=True)
