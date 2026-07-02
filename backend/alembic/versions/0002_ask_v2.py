"""ask flow v2: clarification statuses, retries, summaries, suggested questions

- query_history.generated_sql becomes nullable (clarification turns have no SQL)
- query_history gains response_status / clarification_json / retry_count / summary_text
- schema_snapshots gains suggested_questions_json

``0001_initial`` creates tables with ``Base.metadata.create_all``, so a fresh
database already has these columns when this migration runs — every step here
checks the live schema first and no-ops when the change is already present.

Revision ID: 0002_ask_v2
Revises: 0001_initial
Create Date: 2026-07-02 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_ask_v2"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> dict[str, dict]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"]: column for column in inspector.get_columns(table)}


def upgrade() -> None:
    history = _columns("query_history")

    if history["generated_sql"]["nullable"] is False:
        op.alter_column("query_history", "generated_sql", existing_type=sa.Text(), nullable=True)
    if "response_status" not in history:
        op.add_column(
            "query_history",
            sa.Column("response_status", sa.String(32), nullable=False, server_default="ok"),
        )
    if "clarification_json" not in history:
        op.add_column("query_history", sa.Column("clarification_json", sa.JSON(), nullable=True))
    if "retry_count" not in history:
        op.add_column(
            "query_history",
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "summary_text" not in history:
        op.add_column("query_history", sa.Column("summary_text", sa.Text(), nullable=True))

    snapshots = _columns("schema_snapshots")
    if "suggested_questions_json" not in snapshots:
        op.add_column(
            "schema_snapshots", sa.Column("suggested_questions_json", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    op.drop_column("schema_snapshots", "suggested_questions_json")
    op.drop_column("query_history", "summary_text")
    op.drop_column("query_history", "retry_count")
    op.drop_column("query_history", "clarification_json")
    op.drop_column("query_history", "response_status")
    op.execute("UPDATE query_history SET generated_sql = '' WHERE generated_sql IS NULL")
    op.alter_column("query_history", "generated_sql", existing_type=sa.Text(), nullable=False)
