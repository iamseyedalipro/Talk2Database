"""Execute an accepted SQL statement and return rows (or a CSV download)."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus
from app.schemas.execute import ExecuteRequest, ExecuteResponse, ResultColumn
from app.services.csv_export import stream_csv
from app.services.query_runner import run_select
from app.services.sql_guard import SqlGuardError, validate_select

router = APIRouter(prefix="/execute", tags=["execute"])


def _effective_max_rows(requested: int | None) -> int:
    cap = get_settings().query_max_rows
    return min(requested, cap) if requested else cap


def _validate(sql: str) -> str:
    try:
        return validate_select(sql)
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only single read-only SELECT statements may be executed: {exc}",
        ) from exc


async def _record_history(
    session: SessionDep,
    user_id: int,
    history_id: int | None,
    *,
    status_value: QueryStatus,
    row_count: int | None = None,
    error: str | None = None,
) -> None:
    if history_id is None:
        return
    history = await session.get(QueryHistory, history_id)
    if history is None or history.user_id != user_id:
        return
    history.last_status = status_value
    history.row_count = row_count
    history.error_message = error
    history.executed_at = datetime.now(tz=UTC)


@router.post("", response_model=ExecuteResponse)
async def execute(
    payload: ExecuteRequest, user: CurrentUser, session: SessionDep
) -> ExecuteResponse:
    safe_sql = _validate(payload.sql)
    max_rows = _effective_max_rows(payload.max_rows)

    try:
        result = await run_in_threadpool(run_select, safe_sql, max_rows)
    except psycopg.Error as exc:
        await _record_history(
            session, user.id, payload.history_id, status_value=QueryStatus.ERROR, error=str(exc)
        )
        await session.commit()  # persist the error status before the request unwinds
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Query failed: {exc}"
        ) from exc

    await _record_history(
        session,
        user.id,
        payload.history_id,
        status_value=QueryStatus.SUCCESS,
        row_count=result.row_count,
    )
    return ExecuteResponse(
        columns=[ResultColumn(name=name, type=type_) for name, type_ in result.columns],
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )


@router.post("/csv")
async def execute_csv(payload: ExecuteRequest, _: CurrentUser) -> StreamingResponse:
    safe_sql = _validate(payload.sql)
    max_rows = _effective_max_rows(payload.max_rows)
    return StreamingResponse(
        stream_csv(safe_sql, max_rows),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="talk2database_result.csv"'},
    )
