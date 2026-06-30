"""Execute an accepted SQL statement and return rows (or a CSV download)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.connectors import Connector, ConnectorQueryError
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus
from app.schemas.execute import ExecuteRequest, ExecuteResponse, ResultColumn
from app.services.connections import load_connector
from app.services.sql_guard import SqlGuardError

router = APIRouter(prefix="/execute", tags=["execute"])


def _effective_max_rows(requested: int | None) -> int:
    cap = get_settings().query_max_rows
    return min(requested, cap) if requested else cap


def _validate(connector: Connector, sql: str) -> str:
    try:
        return connector.validate(sql)
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
    _, connector = await load_connector(session, payload.connection_id, user)
    safe_sql = _validate(connector, payload.sql)
    max_rows = _effective_max_rows(payload.max_rows)

    try:
        result = await run_in_threadpool(connector.run, safe_sql, max_rows)
    except ConnectorQueryError as exc:
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
async def execute_csv(
    payload: ExecuteRequest, user: CurrentUser, session: SessionDep
) -> StreamingResponse:
    _, connector = await load_connector(session, payload.connection_id, user)
    safe_sql = _validate(connector, payload.sql)
    max_rows = _effective_max_rows(payload.max_rows)
    return StreamingResponse(
        connector.stream_csv(safe_sql, max_rows),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="talk2database_result.csv"'},
    )
