"""Turn a natural-language question into a previewable, read-only SQL SELECT."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models.query_history import QueryHistory, QueryStatus, ResponseStatus
from app.schemas.ask import AskRequest, AskResponse, SuggestedInterpretationOut
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_ai_provider
from app.services.ai.generate import generate_with_verification
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
                f"No tables found in database '{connection.database}' "
                f"on {connection.host}:{connection.port}. "
                "Check that the database name is correct and that it contains tables. "
                "If your tables are in a specific schema, set it in the connection's Schemas field."
            ),
        )

    schema_data = cast(SchemaData, snapshot.content_json)
    selected = select_schema(schema_data, payload.question, settings.schema_max_tokens)

    provider = get_ai_provider()
    try:
        outcome = await generate_with_verification(
            provider=provider,
            connector=connector,
            question=payload.question,
            full_schema=schema_data,
            selected_text=selected.text,
            settings=settings,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SqlGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The generated statement is not a single read-only SELECT: {exc}",
        ) from exc

    result = outcome.result
    interpretations = [
        SuggestedInterpretationOut(label=i.label, description=i.description)
        for i in (result.suggested_interpretations or [])
    ]

    if result.status != "ok":
        response_status = ResponseStatus(result.status).value
        clarification_json = {
            "clarification_question": result.clarification_question,
            "suggested_interpretations": [i.model_dump() for i in interpretations],
        }
        generated_sql: str | None = None
        invalid_identifiers: list[str] = []
    elif outcome.verification is not None:
        # Retries exhausted; surface the last SQL so the user can hand-fix it.
        response_status = ResponseStatus.VERIFICATION_FAILED.value
        clarification_json = None
        generated_sql = outcome.safe_sql
        invalid_identifiers = (
            outcome.verification.unknown_tables + outcome.verification.unknown_columns
        )
    else:
        response_status = ResponseStatus.OK.value
        clarification_json = None
        generated_sql = outcome.safe_sql
        invalid_identifiers = []

    history = QueryHistory(
        user_id=user.id,
        connection_id=connection.id,
        question=payload.question,
        generated_sql=generated_sql,
        response_status=response_status,
        clarification_json=clarification_json,
        retry_count=outcome.retry_count,
        provider=provider.name,
        model=provider.model,
        last_status=QueryStatus.PREVIEW,
    )
    session.add(history)
    await session.flush()

    warnings = list(selected.warnings)
    if response_status == ResponseStatus.VERIFICATION_FAILED.value and outcome.verification:
        warnings.append(
            "The generated SQL references identifiers that do not exist: "
            + outcome.verification.describe()
        )

    return AskResponse(
        history_id=history.id,
        status=response_status,
        generated_sql=generated_sql,
        explanation=result.explanation,
        clarification_question=result.clarification_question,
        suggested_interpretations=interpretations,
        invalid_identifiers=invalid_identifiers,
        retry_count=outcome.retry_count,
        dialect=connector.dialect,
        provider=provider.name,
        model=provider.model,
        warnings=warnings,
    )
