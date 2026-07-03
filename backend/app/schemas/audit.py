"""Schema for the admin audit feed over query history."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.query_history import QueryStatus


class AuditItem(BaseModel):
    """A single audited query. No row data is included (none is stored)."""

    id: int
    user_id: int
    user_email: str | None = None
    connection_id: int | None = None
    question: str
    generated_sql: str
    provider: str | None = None
    model: str | None = None
    last_status: QueryStatus
    error_message: str | None = None
    row_count: int | None = None
    executed_at: datetime | None = None
    created_at: datetime
