"""Schemas for the admin token-usage monitoring report."""

from __future__ import annotations

from pydantic import BaseModel


class UsageTotals(BaseModel):
    """Summed token counts over the selected window."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class UsageByKey(BaseModel):
    """Totals grouped by one dimension (user, model, or provider)."""

    key: str
    label: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class UsageDailyPoint(BaseModel):
    """One day's totals for the time-series chart."""

    day: str  # ISO date (YYYY-MM-DD)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


class UsageReport(BaseModel):
    """The full monitoring payload returned by ``GET /admin/usage``."""

    totals: UsageTotals
    by_user: list[UsageByKey]
    by_model: list[UsageByKey]
    by_provider: list[UsageByKey]
    daily: list[UsageDailyPoint]
