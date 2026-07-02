"""Schemas for the natural-language answer summary step."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    """The client sends back the result it already holds — nothing is re-executed.

    The server truncates rows/columns/cells to the configured caps before
    anything reaches the AI provider, regardless of what the client sends.
    """

    connection_id: int
    history_id: int | None = None
    question: str = Field(min_length=1, max_length=4000)
    sql: str = Field(min_length=1, max_length=20000)
    columns: list[str] = Field(max_length=200)
    rows: list[list[Any]] = Field(max_length=1000)
    row_count: int = Field(ge=0)
    truncated: bool = False


class SummarizeResponse(BaseModel):
    summary: str
