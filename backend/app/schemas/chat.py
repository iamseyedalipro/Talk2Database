"""Schemas for persistent Ask chat sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.ask import AskResponse


class ChatSessionCreate(BaseModel):
    connection_id: int
    title: str | None = Field(default=None, max_length=200)


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class ChatSessionItem(BaseModel):
    id: int
    title: str
    connection_id: int | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class ChatMessageItem(BaseModel):
    id: int
    role: str
    # The question text (user turns).
    content: str | None = None
    # The stored AskResponse dump (assistant turns).
    ask: dict[str, Any] | None = None
    history_id: int | None = None
    executed_sql: str | None = None
    result_sample: dict[str, Any] | None = None
    created_at: datetime


class ChatAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatAskResponse(AskResponse):
    """The generation result plus the persisted message ids for this turn."""

    user_message_id: int
    assistant_message_id: int
    session_title: str
