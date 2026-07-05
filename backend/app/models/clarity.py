"""Stored Microsoft Clarity data and the log of daily fetch runs.

The Clarity Data Export API allows only 10 requests per project per day, so
each end-of-day run spends that budget on a configurable list of dimension
combinations and stores the raw JSON responses (:class:`ClaritySnapshot`)
grouped under one :class:`ClarityFetchRun`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ClarityFetchRun(Base, TimestampMixin):
    __tablename__ = "clarity_fetch_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # scheduled | manual
    data_date: Mapped[date] = mapped_column(Date, nullable=False)
    # running | success | partial | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    requests_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requests_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClaritySnapshot(Base, TimestampMixin):
    __tablename__ = "clarity_snapshots"
    __table_args__ = (Index("ix_clarity_snapshots_date_combo", "data_date", "combo_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fetch_run_id: Mapped[int] = mapped_column(
        ForeignKey("clarity_fetch_runs.id", ondelete="CASCADE"), nullable=False
    )
    data_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Human-readable key for the dimension combination, e.g. "overall" or "URL+Device".
    combo_key: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    num_of_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | error
    payload: Mapped[Any] = mapped_column(JSON, nullable=True)  # raw API response
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
