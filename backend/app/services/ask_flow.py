"""The shared question -> SQL pipeline behind ``POST /ask`` and chat sessions.

Loads the connector, prepares the schema + glossary context, calls the AI
provider with verification/retries, records the audit-log row and token usage,
and shapes the API response. Kept in a service so the stateless ``/ask``
endpoint and the session-aware ``/chats/{id}/ask`` endpoint stay in lockstep.
"""

from __future__ import annotations

import logging
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.query_history import QueryHistory, QueryStatus, ResponseStatus
from app.models.user import User
from app.schemas.ask import AskResponse, SuggestedInterpretationOut
from app.services.ai.base import AIProviderError, ChatMessage, TokenUsage
from app.services.ai.factory import get_ai_provider
from app.services.ai.generate import generate_with_verification
from app.services.connections import load_connector
from app.services.prompt_store import ASK_PROMPT_KEY, get_prompt, render_ask_system
from app.services.schema.cache import ensure_snapshot
from app.services.schema.discover import DiscoveredSchema, discover_schema
from app.services.schema.glossary import build_glossary_block, load_glossary
from app.services.schema.introspect import SchemaData
from app.services.schema.select import SelectedSchema, select_schema
from app.services.sql_guard import SqlGuardError
from app.services.token_usage import record_usage

logger = logging.getLogger(__name__)


async def run_ask_flow(
    session: AsyncSession,
    user: User,
    connection_id: int,
    question: str,
    *,
    history: list[ChatMessage] | None = None,
    question_context: str | None = None,
) -> AskResponse:
    """Generate previewable, read-only SQL for ``question``.

    ``history`` carries prior conversation turns (chat sessions); ``None`` keeps
    the stateless single-question behavior of ``POST /ask``. ``question_context``
    is an optional data block shown to the model just before the question (the
    stored question/audit text stays clean).
    """
    settings = get_settings()
    connection, connector = await load_connector(session, connection_id, user)

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

    # Ground the model with the connection's business glossary + metrics, when set.
    descriptions, metrics = await load_glossary(session, connection.id)
    glossary_text = build_glossary_block(descriptions, metrics)

    # The system prompt template is admin-editable (stored in the panel DB).
    template, _ = await get_prompt(session, ASK_PROMPT_KEY)
    system_prompt = render_ask_system(template, connector.label)

    provider = get_ai_provider()

    # Choose which tables to send. Discovery (default) shows the model only the
    # table-name directory and lets it request details on demand; otherwise fall
    # back to the lexical relevance trimmer.
    selected: DiscoveredSchema | SelectedSchema
    if settings.ask_schema_discovery:
        selected = await discover_schema(
            provider=provider,
            schema=schema_data,
            question=question,
            ask_system_prompt=system_prompt,
            glossary_text=glossary_text,
            settings=settings,
        )
        discovery_usage = selected.usage
    else:
        selected = select_schema(schema_data, question, settings.schema_max_tokens)
        discovery_usage = TokenUsage()

    schema_text = f"{selected.text}\n\n{glossary_text}" if glossary_text else selected.text

    try:
        outcome = await generate_with_verification(
            provider=provider,
            connector=connector,
            question=question,
            full_schema=schema_data,
            selected_text=schema_text,
            settings=settings,
            system_prompt=system_prompt,
            history=history,
            question_context=question_context,
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

    history_row = QueryHistory(
        user_id=user.id,
        connection_id=connection.id,
        question=question,
        generated_sql=generated_sql,
        response_status=response_status,
        clarification_json=clarification_json,
        retry_count=outcome.retry_count,
        provider=provider.name,
        model=provider.model,
        last_status=QueryStatus.PREVIEW,
    )
    session.add(history_row)
    await session.flush()

    try:
        await record_usage(
            session,
            user_id=user.id,
            connection_id=connection.id,
            operation="generate_sql",
            provider=provider.name,
            model=provider.model,
            usage=discovery_usage + outcome.usage,
        )
    except Exception:  # usage tracking must never fail the request
        logger.exception("Failed to record token usage for /ask")

    warnings = list(selected.warnings)
    if response_status == ResponseStatus.VERIFICATION_FAILED.value and outcome.verification:
        warnings.append(
            "The generated SQL references identifiers that do not exist: "
            + outcome.verification.describe()
        )

    return AskResponse(
        history_id=history_row.id,
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
