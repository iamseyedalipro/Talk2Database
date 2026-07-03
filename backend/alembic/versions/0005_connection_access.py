"""connection access grants (per-user sharing)

Adds the ``connection_access`` join table: an admin can grant a user read/use
access to a connection they do not own. Access lets the grantee ask questions,
run read-only queries, browse the schema, and edit the glossary — but not edit
the connection settings or delete it.

``0001_initial`` builds the panel schema via ``Base.metadata.create_all``, so a
fresh database already has this table when the migration runs; the guard makes
it a no-op there and adds the table to databases initialized before it.

Revision ID: 0005_connection_access
Revises: 0004_ask_v2
Create Date: 2026-07-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0005_connection_access"
down_revision: str | None = "0004_ask_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("connection_access"):
        return

    op.create_table(
        "connection_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
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
        sa.UniqueConstraint("connection_id", "user_id", name="uq_connection_access"),
    )
    op.create_index("ix_connection_access_connection_id", "connection_access", ["connection_id"])
    op.create_index("ix_connection_access_user_id", "connection_access", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("connection_access"):
        return
    op.drop_index("ix_connection_access_user_id", table_name="connection_access")
    op.drop_index("ix_connection_access_connection_id", table_name="connection_access")
    op.drop_table("connection_access")
