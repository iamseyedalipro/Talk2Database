"""chat sessions

Adds the persistent Ask conversation tables (``chat_sessions``,
``chat_messages``).

Guarded with ``has_table`` because 0001 creates every registered model via
``Base.metadata.create_all`` — on a fresh database these tables already exist
by the time this revision runs.

Revision ID: 0008_chat_sessions
Revises: 0007_clarity_and_settings
Create Date: 2026-07-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_chat_sessions"
down_revision: str | None = "0007_clarity_and_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("chat_sessions"):
        op.create_table(
            "chat_sessions",
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
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
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
        op.create_index(
            "ix_chat_sessions_user_updated",
            "chat_sessions",
            ["user_id", "updated_at"],
        )

    if not inspector.has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("ask_json", sa.JSON(), nullable=True),
            sa.Column(
                "history_id",
                sa.Integer(),
                sa.ForeignKey("query_history.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("executed_sql", sa.Text(), nullable=True),
            sa.Column("result_sample_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_chat_messages_session_id",
            "chat_messages",
            ["session_id", "id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("chat_messages"):
        op.drop_table("chat_messages")
    if inspector.has_table("chat_sessions"):
        op.drop_table("chat_sessions")
