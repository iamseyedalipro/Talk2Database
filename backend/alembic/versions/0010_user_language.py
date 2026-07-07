"""user language preference

Adds ``users.language`` ("en" | "fa"), the per-user UI language that also
drives RTL layout in the panel.

Guarded with a column inspection because 0001 creates every registered model
via ``Base.metadata.create_all`` — on a fresh database the column already
exists by the time this revision runs.

Revision ID: 0010_user_language
Revises: 0009_dashboards
Create Date: 2026-07-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_user_language"
down_revision: str | None = "0009_dashboards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("users", "language"):
        op.add_column(
            "users",
            sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        )


def downgrade() -> None:
    if _has_column("users", "language"):
        op.drop_column("users", "language")
