"""Saved queries (the "Questions" library): bookmark a vetted query and re-run
it without re-asking the AI.

Visibility: a user always sees their own saved queries plus any that other users
have marked ``shared``. Editing/deleting is restricted to the owner, except that
an admin may also manage a *shared* query (light moderation).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.connectors import ConnectorQueryError
from app.deps import CurrentUser, SessionDep
from app.models.saved_query import SavedQuery
from app.models.user import User
from app.schemas.execute import ExecuteResponse, ResultColumn
from app.schemas.saved_query import (
    SavedQueryCreate,
    SavedQueryItem,
    SavedQueryRunRequest,
    SavedQueryUpdate,
)
from app.services.connections import load_connector
from app.services.sql_guard import SqlGuardError

router = APIRouter(prefix="/saved-queries", tags=["saved-queries"])


def can_view(user: User, sq: SavedQuery) -> bool:
    """A user may view their own saved queries and any shared one."""
    return sq.owner_id == user.id or sq.shared


def can_edit(user: User, sq: SavedQuery) -> bool:
    """The owner may always edit/delete; an admin may manage a *shared* one."""
    return sq.owner_id == user.id or (user.is_admin and sq.shared)


def _to_item(sq: SavedQuery, user: User, owner_email: str | None) -> SavedQueryItem:
    item = SavedQueryItem.model_validate(sq)
    item.owner_email = owner_email
    item.is_owner = sq.owner_id == user.id
    return item


async def _get_visible(session: SessionDep, user: User, saved_query_id: int) -> SavedQuery:
    sq = await session.get(SavedQuery, saved_query_id)
    if sq is None or not can_view(user, sq):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found.")
    return sq


@router.get("", response_model=list[SavedQueryItem])
async def list_saved_queries(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SavedQueryItem]:
    result = await session.execute(
        select(SavedQuery, User.email)
        .join(User, User.id == SavedQuery.owner_id)
        .where(or_(SavedQuery.owner_id == user.id, SavedQuery.shared.is_(True)))
        .order_by(SavedQuery.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_to_item(sq, user, email) for sq, email in result.all()]


@router.post("", response_model=SavedQueryItem, status_code=status.HTTP_201_CREATED)
async def create_saved_query(
    payload: SavedQueryCreate, user: CurrentUser, session: SessionDep
) -> SavedQueryItem:
    sq = SavedQuery(
        owner_id=user.id,
        connection_id=payload.connection_id,
        name=payload.name,
        question=payload.question,
        generated_sql=payload.generated_sql,
        shared=payload.shared,
    )
    session.add(sq)
    await session.flush()
    return _to_item(sq, user, user.email)


@router.get("/{saved_query_id}", response_model=SavedQueryItem)
async def get_saved_query(
    saved_query_id: int, user: CurrentUser, session: SessionDep
) -> SavedQueryItem:
    sq = await _get_visible(session, user, saved_query_id)
    owner_email = await session.scalar(select(User.email).where(User.id == sq.owner_id))
    return _to_item(sq, user, owner_email)


@router.patch("/{saved_query_id}", response_model=SavedQueryItem)
async def update_saved_query(
    saved_query_id: int,
    payload: SavedQueryUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> SavedQueryItem:
    sq = await session.get(SavedQuery, saved_query_id)
    if sq is None or not can_view(user, sq):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found.")
    if not can_edit(user, sq):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this saved query.",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sq, field, value)
    await session.flush()
    owner_email = await session.scalar(select(User.email).where(User.id == sq.owner_id))
    return _to_item(sq, user, owner_email)


@router.delete("/{saved_query_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_query(
    saved_query_id: int, user: CurrentUser, session: SessionDep
) -> Response:
    sq = await session.get(SavedQuery, saved_query_id)
    if sq is None or not can_view(user, sq):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found.")
    if not can_edit(user, sq):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this saved query.",
        )
    await session.delete(sq)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{saved_query_id}/run", response_model=ExecuteResponse)
async def run_saved_query(
    saved_query_id: int,
    payload: SavedQueryRunRequest,
    user: CurrentUser,
    session: SessionDep,
) -> ExecuteResponse:
    sq = await _get_visible(session, user, saved_query_id)
    if sq.connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The connection for this saved query no longer exists.",
        )
    # Re-run executes the stored SQL directly — no AI call. Connections are
    # per-owner, so a shared query can only be run by someone who owns its
    # bound connection; otherwise we surface a clear, non-leaky message.
    try:
        _, connector = await load_connector(session, sq.connection_id, user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND and sq.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This shared query is bound to a connection you don't own. "
                    "Copy its SQL into the SQL editor to run it against your own connection."
                ),
            ) from exc
        raise

    try:
        safe_sql = connector.validate(sq.generated_sql)
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only single read-only SELECT statements may be executed: {exc}",
        ) from exc

    cap = get_settings().query_max_rows
    max_rows = min(payload.max_rows, cap) if payload.max_rows else cap

    try:
        result = await run_in_threadpool(connector.run, safe_sql, max_rows)
    except ConnectorQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Query failed: {exc}"
        ) from exc

    return ExecuteResponse(
        columns=[ResultColumn(name=name, type=type_) for name, type_ in result.columns],
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )
