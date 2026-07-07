"""Persistent Ask conversations (ChatGPT-style sessions).

Sessions are strictly per-user. Asking inside a session prepends the stored
conversation history (questions, generated SQL, and capped result samples) to
the model's message list so follow-ups like "only phone and name" refine the
previous statement.

This is the HTTP transport; the same session-aware flow streams live progress
over the WebSocket when the client passes a ``chat_id`` (see
:mod:`app.routers.ask_ws`). The shared pieces live in
:mod:`app.services.chat_context`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

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
from app.services.ask_flow import AskFlowError, run_ask_flow
from app.services.chat_context import (
    DEFAULT_TITLE,
    get_own_chat_session,
    load_chat_context,
    persist_chat_turn,
    require_askable,
)
from app.services.connections import load_connector

router = APIRouter(prefix="/chats", tags=["chats"])


def _to_item(row: ChatSession) -> ChatSessionItem:
    return ChatSessionItem(
        id=row.id,
        title=row.title,
        connection_id=row.connection_id,
        archived=row.archived,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


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
        title=(payload.title or "").strip() or DEFAULT_TITLE,
    )
    session.add(chat)
    await session.flush()
    return _to_item(chat)


@router.patch("/{chat_id}", response_model=ChatSessionItem)
async def update_chat(
    chat_id: int, payload: ChatSessionUpdate, user: CurrentUser, session: SessionDep
) -> ChatSessionItem:
    chat = await get_own_chat_session(session, user.id, chat_id)
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
    chat = await get_own_chat_session(session, user.id, chat_id)
    # Messages cascade; QueryHistory rows survive via SET NULL.
    await session.delete(chat)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{chat_id}/messages", response_model=list[ChatMessageItem])
async def list_messages(
    chat_id: int, user: CurrentUser, session: SessionDep
) -> list[ChatMessageItem]:
    await get_own_chat_session(session, user.id, chat_id)
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
    chat = await get_own_chat_session(session, user.id, chat_id)
    connection_id = require_askable(chat)
    history, question_context = await load_chat_context(session, chat.id)

    try:
        outcome = await run_ask_flow(
            session,
            user,
            connection_id=connection_id,
            question=payload.question,
            history=history,
            question_context=question_context,
        )
    except AskFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response = outcome.response

    user_message_id, assistant_message_id = await persist_chat_turn(
        session, chat, payload.question, response
    )
    return ChatAskResponse(
        **response.model_dump(),
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        session_title=chat.title,
    )
