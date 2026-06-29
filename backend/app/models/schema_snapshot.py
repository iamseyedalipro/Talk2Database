"""Persisted snapshot of the user-data schema.

The schema is introspected **once per import** and stored here, so questions
never trigger a re-introspection and the serialized text can be reused as a
cacheable prompt prefix. See ``app/services/schema``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SchemaSnapshot(Base, TimestampMixin):
    __tablename__ = "schema_snapshots"
    __table_args__ = (Index("ix_schema_snapshots_version", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Monotonically increasing; the highest version is the current schema.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stable hash of the structure; identical structure => identical fingerprint.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Canonical, deterministically-sorted text block sent to the AI.
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured form used for relevance trimming and FK expansion.
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
