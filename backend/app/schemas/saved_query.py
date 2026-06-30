"""Schemas for the saved-query (Questions) library."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    generated_sql: str = Field(min_length=1, max_length=20000)
    connection_id: int | None = None
    question: str | None = Field(default=None, max_length=20000)
    shared: bool = False


class SavedQueryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    generated_sql: str | None = Field(default=None, min_length=1, max_length=20000)
    connection_id: int | None = None
    question: str | None = Field(default=None, max_length=20000)
    shared: bool | None = None


class SavedQueryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    owner_email: str | None = None
    connection_id: int | None = None
    name: str
    question: str | None = None
    generated_sql: str
    shared: bool
    is_owner: bool = False
    created_at: datetime


class SavedQueryRunRequest(BaseModel):
    max_rows: int | None = Field(default=None, ge=1, le=100000)
