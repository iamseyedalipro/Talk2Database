"""clarity data + app settings

Adds the generic ``app_settings`` key/value table and the Microsoft Clarity
storage tables (``clarity_fetch_runs``, ``clarity_snapshots``).

Guarded with ``has_table`` because 0001 creates every registered model via
``Base.metadata.create_all`` — on a fresh database these tables already exist
by the time this revision runs.

Revision ID: 0002_clarity_and_settings
Revises: 0001_initial
Create Date: 2026-07-02 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_clarity_and_settings"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("app_settings"):
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(length=100), primary_key=True),
            sa.Column("value", sa.JSON(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if not inspector.has_table("clarity_fetch_runs"):
        op.create_table(
            "clarity_fetch_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("trigger", sa.String(length=16), nullable=False),
            sa.Column("data_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("requests_attempted", sa.Integer(), nullable=False),
            sa.Column("requests_succeeded", sa.Integer(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if not inspector.has_table("clarity_snapshots"):
        op.create_table(
            "clarity_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "fetch_run_id",
                sa.Integer(),
                sa.ForeignKey("clarity_fetch_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("data_date", sa.Date(), nullable=False),
            sa.Column("combo_key", sa.String(length=120), nullable=False),
            sa.Column("dimensions", sa.JSON(), nullable=False),
            sa.Column("num_of_days", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_clarity_snapshots_date_combo",
            "clarity_snapshots",
            ["data_date", "combo_key"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("clarity_snapshots"):
        op.drop_table("clarity_snapshots")
    if inspector.has_table("clarity_fetch_runs"):
        op.drop_table("clarity_fetch_runs")
    if inspector.has_table("app_settings"):
        op.drop_table("app_settings")
