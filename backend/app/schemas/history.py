"""Schemas for query history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.query_history import QueryStatus


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int | None = None
    question: str
    # NULL for clarification/unanswerable turns that produced no SQL.
    generated_sql: str | None = None
    response_status: str = "ok"
    clarification_json: dict[str, Any] | None = None
    retry_count: int = 0
    provider: str | None = None
    model: str | None = None
    last_status: QueryStatus
    error_message: str | None = None
    row_count: int | None = None
    executed_at: datetime | None = None
    rerun_of_id: int | None = None
    created_at: datetime


class RerunRequest(BaseModel):
    # Optional edited SQL; when omitted the stored SQL is re-run.
    sql: str | None = Field(default=None, max_length=20000)
    max_rows: int | None = Field(default=None, ge=1, le=100000)
