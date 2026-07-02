"""A bookmarked, vetted query that can be re-run without re-asking the AI.

Saved queries turn one-off questions into reusable reports. Each is owned by a
user; ``shared=True`` makes it visible (and runnable) by every panel user.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SavedQuery(Base, TimestampMixin):
    __tablename__ = "saved_queries"
    __table_args__ = (Index("ix_saved_queries_owner_created", "owner_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The connection the query was vetted against; SET NULL if it is deleted.
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The original natural-language question (optional context for the reader).
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
