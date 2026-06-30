"""System status schema."""

from __future__ import annotations

from pydantic import BaseModel


class SystemStatus(BaseModel):
    provider: str
    model: str
    connection_count: int
    supported_types: list[str]
