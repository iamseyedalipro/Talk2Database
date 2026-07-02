"""System status schema."""

from __future__ import annotations

from pydantic import BaseModel


class SystemStatus(BaseModel):
    provider: str
    model: str
    connection_count: int
    supported_types: list[str]
    # Whether POST /api/summarize is available (sends capped result samples to the AI).
    answer_summary_enabled: bool = False
