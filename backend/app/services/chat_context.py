"""Shared chat-session plumbing for the HTTP and WebSocket ask transports.

Both ``POST /chats/{id}/ask`` and the ``chat_id``-carrying WebSocket ask need
the same three things: load-and-authorize the session, turn its stored
messages into LLM context, and persist the finished turn. Keeping them here
guarantees the two transports never drift.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chat import ChatMessage, ChatSession
from app.schemas.ask import AskResponse
from app.services.ai.base import ChatMessage as LLMMessage
from app.services.ai.prompts import (
    build_history_turn_assistant,
    build_history_turn_user,
    build_result_context,
)

DEFAULT_TITLE = "New chat"


async def get_own_chat_session(session: AsyncSession, user_id: int, chat_id: int) -> ChatSession:
    """The caller's own chat session, or 404 (never leaks other users' chats)."""
    chat = await session.get(ChatSession, chat_id)
    if chat is None or chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


def require_askable(chat: ChatSession) -> int:
    """Validate that a session can take a new question; return its connection id."""
    if chat.archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This chat is archived. Unarchive it to continue the conversation.",
        )
    if chat.connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This chat's data source was deleted; start a new chat.",
        )
    return chat.connection_id


def build_history_messages(
    rows: list[ChatMessage],
    *,
    max_turns: int,
    max_chars: int,
    include_samples: bool,
) -> list[LLMMessage]:
    """Convert stored messages into the LLM history, newest-biased.

    Keeps the last ``max_turns`` user+assistant pairs, then drops the oldest
    pairs until the rendered text fits ``max_chars``. A user turn carries the
    result sample of the *preceding* executed assistant turn, so the model can
    reason about data the user is reacting to.
    """
    pairs: list[tuple[ChatMessage, ChatMessage | None]] = []
    pending_user: ChatMessage | None = None
    for row in rows:
        if row.role == "user":
            if pending_user is not None:
                pairs.append((pending_user, None))
            pending_user = row
        elif row.role == "assistant" and pending_user is not None:
            pairs.append((pending_user, row))
            pending_user = None
    if pending_user is not None:
        pairs.append((pending_user, None))

    pairs = pairs[-max_turns:]

    def render(selected: list[tuple[ChatMessage, ChatMessage | None]]) -> list[LLMMessage]:
        messages: list[LLMMessage] = []
        prev_assistant: ChatMessage | None = None
        for user_row, assistant_row in selected:
            sample = (
                prev_assistant.result_sample_json
                if include_samples and prev_assistant is not None
                else None
            )
            messages.append(
                {
                    "role": "user",
                    "content": build_history_turn_user(user_row.content or "", sample),
                }
            )
            if assistant_row is not None and assistant_row.ask_json is not None:
                messages.append(
                    {
                        "role": "assistant",
                        "content": build_history_turn_assistant(assistant_row.ask_json),
                    }
                )
            prev_assistant = assistant_row
        return messages

    messages = render(pairs)
    while pairs and sum(len(m["content"]) for m in messages) > max_chars:
        pairs = pairs[1:]
        messages = render(pairs)
    return messages


def latest_result_sample(
    rows: list[ChatMessage], *, include_samples: bool
) -> dict[str, object] | None:
    """The sample from the most recent executed assistant turn, for the current
    question's context block."""
    if not include_samples:
        return None
    for row in reversed(rows):
        if row.role == "assistant" and row.result_sample_json is not None:
            return row.result_sample_json
    return None


async def load_chat_context(
    session: AsyncSession, chat_id: int
) -> tuple[list[LLMMessage] | None, str | None]:
    """The (history, question_context) pair for the next question in a session."""
    settings = get_settings()
    rows = list(
        (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat_id)
                .order_by(ChatMessage.id)
            )
        ).all()
    )
    include_samples = settings.chat_context_sample_rows_enabled
    history = build_history_messages(
        rows,
        max_turns=settings.chat_history_max_turns,
        max_chars=settings.chat_history_max_chars,
        include_samples=include_samples,
    )
    # The freshest executed result rides along with the *current* question.
    current_sample = latest_result_sample(rows, include_samples=include_samples)
    question_context = build_result_context(current_sample) if current_sample else None
    return (history or None), question_context


async def persist_chat_turn(
    session: AsyncSession,
    chat: ChatSession,
    question: str,
    response: AskResponse,
) -> tuple[int, int]:
    """Store the finished user+assistant turn; returns their message ids.

    Also auto-titles the session from its first question and bumps its
    recency. The caller owns the commit.
    """
    user_msg = ChatMessage(session_id=chat.id, role="user", content=question)
    session.add(user_msg)
    assistant_msg = ChatMessage(
        session_id=chat.id,
        role="assistant",
        ask_json=response.model_dump(mode="json"),
        history_id=response.history_id,
    )
    session.add(assistant_msg)

    # First question names the chat (like ChatGPT), unless the user renamed it.
    if chat.title == DEFAULT_TITLE:
        chat.title = question.strip()[:60] or DEFAULT_TITLE
    chat.updated_at = datetime.now(tz=UTC)
    await session.flush()
    return user_msg.id, assistant_msg.id
