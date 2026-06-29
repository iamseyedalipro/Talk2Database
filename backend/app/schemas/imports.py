"""Schemas for imports and system status."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.import_run import ImportKind, ImportStatus


class ImportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ImportKind
    status: ImportStatus
    filename: str | None = None
    bytes: int | None = None
    message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class UploadAccepted(BaseModel):
    import_run_id: int
    status: ImportStatus


class SystemStatus(BaseModel):
    import_mode: str
    provider: str
    model: str
    userdata_connected: bool
    schema_table_count: int
    schema_version: int | None = None
    last_import: ImportRunOut | None = None
