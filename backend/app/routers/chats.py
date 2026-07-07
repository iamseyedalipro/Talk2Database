"""Persistent Ask conversations (ChatGPT-style sessions).

Sessions are strictly per-user. Asking inside a session prepends the stored
conversation history (questions, generated SQL, and capped result samples) to
the model's message list so follow-ups like "only phone and name" refine the
previous statement.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.chat import ChatMessage as ChatMessageRow
from app.models.chat import ChatSession
from app.schemas.chat import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessageItem,
    ChatSessionCreate,
    ChatSessionItem,
    ChatSessionUpdate,
)
from app.services.ai.base import ChatMessage as LLMMessage
from app.services.ai.prompts import (
    build_history_turn_assistant,
    build_history_turn_user,
    build_result_context,
)
from app.services.ask_flow import run_ask_flow
from app.services.connections import load_connector

router = APIRouter(prefix="/chats", tags=["chats"])

_DEFAULT_TITLE = "New chat"


def _to_item(row: ChatSession) -> ChatSessionItem:
    return ChatSessionItem(
        id=row.id,
        title=row.title,
        connection_id=row.connection_id,
        archived=row.archived,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get_own_session(session: SessionDep, user_id: int, chat_id: int) -> ChatSession:
    chat = await session.get(ChatSession, chat_id)
    if chat is None or chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


def build_history_messages(
    rows: list[ChatMessageRow],
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
    pairs: list[tuple[ChatMessageRow, ChatMessageRow | None]] = []
    pending_user: ChatMessageRow | None = None
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

    def render(selected: list[tuple[ChatMessageRow, ChatMessageRow | None]]) -> list[LLMMessage]:
        messages: list[LLMMessage] = []
        prev_assistant: ChatMessageRow | None = None
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
    rows: list[ChatMessageRow], *, include_samples: bool
) -> dict[str, object] | None:
    """The sample from the most recent executed assistant turn, for the current
    question's context block."""
    if not include_samples:
        return None
    for row in reversed(rows):
        if row.role == "assistant" and row.result_sample_json is not None:
            return row.result_sample_json
    return None


@router.get("", response_model=list[ChatSessionItem])
async def list_chats(
    user: CurrentUser,
    session: SessionDep,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[ChatSessionItem]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    if not include_archived:
        stmt = stmt.where(ChatSession.archived.is_(False))
    rows = (await session.scalars(stmt)).all()
    return [_to_item(r) for r in rows]


@router.post("", response_model=ChatSessionItem, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: ChatSessionCreate, user: CurrentUser, session: SessionDep
) -> ChatSessionItem:
    # Validates existence and the caller's access to the connection.
    await load_connector(session, payload.connection_id, user)
    chat = ChatSession(
        user_id=user.id,
        connection_id=payload.connection_id,
        title=(payload.title or "").strip() or _DEFAULT_TITLE,
    )
    session.add(chat)
    await session.flush()
    return _to_item(chat)


@router.patch("/{chat_id}", response_model=ChatSessionItem)
async def update_chat(
    chat_id: int, payload: ChatSessionUpdate, user: CurrentUser, session: SessionDep
) -> ChatSessionItem:
    chat = await _get_own_session(session, user.id, chat_id)
    if payload.title is not None:
        chat.title = payload.title.strip() or chat.title
    if payload.archived is not None:
        chat.archived = payload.archived
    await session.flush()
    # The UPDATE re-computes updated_at server-side (onupdate); reload it so
    # serializing the response never triggers lazy IO on an expired attribute.
    await session.refresh(chat)
    return _to_item(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: int, user: CurrentUser, session: SessionDep) -> Response:
    chat = await _get_own_session(session, user.id, chat_id)
    # Messages cascade; QueryHistory rows survive via SET NULL.
    await session.delete(chat)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{chat_id}/messages", response_model=list[ChatMessageItem])
async def list_messages(
    chat_id: int, user: CurrentUser, session: SessionDep
) -> list[ChatMessageItem]:
    await _get_own_session(session, user.id, chat_id)
    rows = (
        await session.scalars(
            select(ChatMessageRow)
            .where(ChatMessageRow.session_id == chat_id)
            .order_by(ChatMessageRow.id)
        )
    ).all()
    return [
        ChatMessageItem(
            id=r.id,
            role=r.role,
            content=r.content,
            ask=r.ask_json,
            history_id=r.history_id,
            executed_sql=r.executed_sql,
            result_sample=r.result_sample_json,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{chat_id}/ask", response_model=ChatAskResponse)
async def ask_in_chat(
    chat_id: int, payload: ChatAskRequest, user: CurrentUser, session: SessionDep
) -> ChatAskResponse:
    settings = get_settings()
    chat = await _get_own_session(session, user.id, chat_id)
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

    rows = list(
        (
            await session.scalars(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == chat_id)
                .order_by(ChatMessageRow.id)
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

    response = await run_ask_flow(
        session,
        user,
        chat.connection_id,
        payload.question,
        history=history if history else None,
        question_context=question_context,
    )

    user_msg = ChatMessageRow(session_id=chat.id, role="user", content=payload.question)
    session.add(user_msg)
    assistant_msg = ChatMessageRow(
        session_id=chat.id,
        role="assistant",
        ask_json=response.model_dump(mode="json"),
        history_id=response.history_id,
    )
    session.add(assistant_msg)

    # First question names the chat (like ChatGPT), unless the user renamed it.
    if chat.title == _DEFAULT_TITLE:
        chat.title = payload.question.strip()[:60] or _DEFAULT_TITLE
    chat.updated_at = datetime.now(tz=UTC)
    await session.flush()

    return ChatAskResponse(
        **response.model_dump(),
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
        session_title=chat.title,
    )
