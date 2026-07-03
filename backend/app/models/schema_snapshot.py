"""Persisted snapshot of a connection's schema.

The schema is introspected from the live data source and stored here per
connection, so questions reuse the serialized text as a cacheable prompt prefix
instead of re-introspecting on every request. See ``app/services/schema``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SchemaSnapshot(Base, TimestampMixin):
    __tablename__ = "schema_snapshots"
    __table_args__ = (Index("ix_schema_snapshots_connection_version", "connection_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), nullable=False
    )
    # Monotonically increasing per connection; the highest version is current.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stable hash of the structure; identical structure => identical fingerprint.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Canonical, deterministically-sorted text block sent to the AI.
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured form used for relevance trimming and FK expansion.
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cached AI-generated example questions for this exact schema version.
    # A schema change creates a new snapshot row, so the cache self-invalidates.
    suggested_questions_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
