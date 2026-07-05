"""Schemas for the panel-editable prompt templates."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PromptOut(BaseModel):
    key: str
    title: str
    description: str
    content: str
    default_content: str
    is_customized: bool


class PromptUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
