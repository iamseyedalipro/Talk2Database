"""Schemas for the natural-language -> SQL generation step."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class AskResponse(BaseModel):
    history_id: int
    generated_sql: str
    explanation: str | None = None
    dialect: str = "postgres"
    provider: str
    model: str
    # Non-fatal notes, e.g. "schema was trimmed to the most relevant tables".
    warnings: list[str] = Field(default_factory=list)
