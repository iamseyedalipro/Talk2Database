"""Schemas for AI-explained results (summary + chart suggestion)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.execute import ResultColumn


class SummarizeRequest(BaseModel):
    question: str | None = Field(default=None, max_length=20000)
    columns: list[ResultColumn]
    rows: list[list[Any]]
