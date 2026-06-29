"""Per-user query history: list, fetch, and re-run (optionally edited)."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus
from app.schemas.execute import ExecuteResponse, ResultColumn
from app.schemas.history import HistoryItem, RerunRequest
from app.services.query_runner import run_select
from app.services.sql_guard import SqlGuardError, validate_select

router = APIRouter(prefix="/history", tags=["history"])


async def _owned_history(session: SessionDep, user_id: int, history_id: int) -> QueryHistory:
    history = await session.get(QueryHistory, history_id)
    if history is None or history.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History item not found.")
    return history


@router.get("", response_model=list[HistoryItem])
async def list_history(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[QueryHistory]:
    result = await session.execute(
        select(QueryHistory)
        .where(QueryHistory.user_id == user.id)
        .order_by(QueryHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/{history_id}", response_model=HistoryItem)
async def get_history(history_id: int, user: CurrentUser, session: SessionDep) -> QueryHistory:
    return await _owned_history(session, user.id, history_id)


@router.post("/{history_id}/rerun", response_model=ExecuteResponse)
async def rerun_history(
    history_id: int, payload: RerunRequest, user: CurrentUser, session: SessionDep
) -> ExecuteResponse:
    original = await _owned_history(session, user.id, history_id)

    try:
        safe_sql = validate_select(payload.sql or original.generated_sql)
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only single read-only SELECT statements may be executed: {exc}",
        ) from exc

    settings = get_settings()
    max_rows = (
        min(payload.max_rows, settings.query_max_rows)
        if payload.max_rows
        else (settings.query_max_rows)
    )

    entry = QueryHistory(
        user_id=user.id,
        question=original.question,
        generated_sql=safe_sql,
        provider=original.provider,
        model=original.model,
        last_status=QueryStatus.PREVIEW,
        rerun_of_id=original.id,
    )
    session.add(entry)
    await session.flush()

    try:
        result = await run_in_threadpool(run_select, safe_sql, max_rows)
    except psycopg.Error as exc:
        entry.last_status = QueryStatus.ERROR
        entry.error_message = str(exc)
        entry.executed_at = datetime.now(tz=UTC)
        await session.commit()  # persist the error status before the request unwinds
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Query failed: {exc}"
        ) from exc

    entry.last_status = QueryStatus.SUCCESS
    entry.row_count = result.row_count
    entry.executed_at = datetime.now(tz=UTC)

    return ExecuteResponse(
        columns=[ResultColumn(name=name, type=type_) for name, type_ in result.columns],
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )
