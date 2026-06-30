"""Turn a natural-language question into a previewable, read-only SQL SELECT."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus
from app.schemas.ask import AskRequest, AskResponse
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_ai_provider
from app.services.connections import load_connector
from app.services.schema.cache import ensure_snapshot
from app.services.schema.introspect import SchemaData
from app.services.schema.select import select_schema
from app.services.sql_guard import SqlGuardError

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(payload: AskRequest, user: CurrentUser, session: SessionDep) -> AskResponse:
    settings = get_settings()
    connection, connector = await load_connector(session, payload.connection_id, user)

    try:
        snapshot = await ensure_snapshot(session, connection.id, connector)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not read the schema of '{connection.name}': {exc}",
        ) from exc

    if snapshot.table_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No tables found in database '{connection.database}' on {connection.host}:{connection.port}. "
                "Check that the database name is correct and that it contains tables. "
                "If your tables are in a specific schema, set it in the connection's Schemas field."
            ),
        )

    schema_data = cast(SchemaData, snapshot.content_json)
    selected = select_schema(schema_data, payload.question, settings.schema_max_tokens)

    provider = get_ai_provider()
    try:
        generated = await run_in_threadpool(
            provider.generate_sql,
            question=payload.question,
            system_prompt=connector.system_prompt(),
            schema_block=connector.schema_block(selected.text),
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    try:
        safe_sql = connector.validate(generated.sql)
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The generated statement is not a single read-only SELECT: {exc}",
        ) from exc

    history = QueryHistory(
        user_id=user.id,
        connection_id=connection.id,
        question=payload.question,
        generated_sql=safe_sql,
        provider=provider.name,
        model=provider.model,
        last_status=QueryStatus.PREVIEW,
    )
    session.add(history)
    await session.flush()

    return AskResponse(
        history_id=history.id,
        generated_sql=safe_sql,
        explanation=generated.explanation,
        dialect=connector.dialect,
        provider=provider.name,
        model=provider.model,
        warnings=selected.warnings,
    )
