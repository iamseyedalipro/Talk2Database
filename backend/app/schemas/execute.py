"""Schemas for executing an accepted SQL statement."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    connection_id: int
    sql: str = Field(min_length=1, max_length=20000)
    history_id: int | None = None
    max_rows: int | None = Field(default=None, ge=1, le=100000)


class ResultColumn(BaseModel):
    name: str
    type: str


class ExecuteResponse(BaseModel):
    columns: list[ResultColumn]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
