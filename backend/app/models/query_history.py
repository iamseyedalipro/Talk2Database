"""Per-user record of asked questions and the SQL they produced."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QueryStatus(StrEnum):
    PREVIEW = "preview"  # SQL generated, not yet executed
    SUCCESS = "success"
    ERROR = "error"


class QueryHistory(Base, TimestampMixin):
    __tablename__ = "query_history"
    __table_args__ = (Index("ix_query_history_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus, name="query_status"), nullable=False, default=QueryStatus.PREVIEW
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rerun_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("query_history.id", ondelete="SET NULL"), nullable=True
    )
