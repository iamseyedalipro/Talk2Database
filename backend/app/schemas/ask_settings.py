"""Schemas for the admin-editable Ask analysis mode settings."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.app_settings import (
    ASK_ANALYSIS_ROW_CAP_MAX,
    ASK_ANALYSIS_ROW_CAP_MIN,
)


class AskSettingsOut(BaseModel):
    analysis_mode: bool
    row_cap: int
    row_cap_min: int = ASK_ANALYSIS_ROW_CAP_MIN
    row_cap_max: int = ASK_ANALYSIS_ROW_CAP_MAX


class AskSettingsUpdate(BaseModel):
    analysis_mode: bool
    row_cap: int = Field(ge=ASK_ANALYSIS_ROW_CAP_MIN, le=ASK_ANALYSIS_ROW_CAP_MAX)
