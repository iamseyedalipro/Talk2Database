"""Schemas for Microsoft Clarity settings, fetch runs, and availability."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ClaritySettingsOut(BaseModel):
    # The token itself is never returned; only whether one is stored.
    token_set: bool
    project_id: str | None = None
    fetch_time: str
    timezone: str
    dimension_combos: list[list[str]]
    allowed_dimensions: list[str]
    next_run_at: datetime | None = None


class ClaritySettingsUpdate(BaseModel):
    # All optional: only provided fields change. An empty-string token is ignored
    # so the UI can render a blank password input without wiping the stored one.
    api_token: str | None = None
    project_id: str | None = None
    fetch_time: str | None = Field(default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    timezone: str | None = None
    dimension_combos: list[list[str]] | None = None


class ClaritySnapshotOut(BaseModel):
    combo_key: str
    dimensions: list[str]
    status: str
    error: str | None = None


class ClarityRunOut(BaseModel):
    id: int
    trigger: str
    data_date: date
    status: str
    requests_attempted: int
    requests_succeeded: int
    created_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None
    snapshots: list[ClaritySnapshotOut] = Field(default_factory=list)


class ClarityStatusOut(BaseModel):
    configured: bool
    requests_used_today: int
    daily_budget: int
    latest_data_date: str | None = None
    days_stored: int
    next_run_at: datetime | None = None


class ClarityAvailabilityOut(BaseModel):
    available: bool
    latest_data_date: str | None = None
    days_stored: int
