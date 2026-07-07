"""Persistent Ask conversations: sessions and their messages.

A :class:`ChatSession` is one conversation between a user and a single data
source. Its :class:`ChatMessage` rows hold both sides of the exchange — the
user's questions and the assistant's structured answers — plus, once a
statement is executed, a small result sample that later turns feed back to the
model as conversational context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The data source the conversation is about; SET NULL if it is deleted.
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Bumped on every new message so the sidebar sorts by recent activity.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_id", "session_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # The question text (user turns only).
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full AskResponse dump (assistant turns only) so the UI restores verbatim.
    ask_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # The audit-log row this turn produced; the log outlives deleted chats.
    history_id: Mapped[int | None] = mapped_column(
        ForeignKey("query_history.id", ondelete="SET NULL"), nullable=True
    )
    # Set when the user ran the statement: the exact SQL plus a capped sample of
    # the result ({columns, rows, row_count, truncated}) for follow-up context.
    executed_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_sample_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
