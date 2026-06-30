"""Request/response schemas for the connection registry.

Secrets only ever travel **inbound** (``password``); they are never returned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.connection import DataSourceType


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: DataSourceType
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=0, max_length=1024)
    options: dict[str, Any] = Field(default_factory=dict)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: DataSourceType | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, min_length=1, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    # Omit to keep the stored password; provide to rotate it.
    password: str | None = Field(default=None, max_length=1024)
    options: dict[str, Any] | None = None


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: DataSourceType
    host: str
    port: int
    database: str
    username: str
    options: dict[str, Any]
    created_at: datetime


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str | None = None
