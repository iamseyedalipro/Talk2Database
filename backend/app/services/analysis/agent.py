"""The analysis agent: answer analytical questions grounded in real data.

The user picks the data sources per question - stored Microsoft Clarity
metrics and/or their registered database connections. Clarity context is
inlined into the system prompt; databases are exposed through a single
``run_sql`` tool the model may call up to :data:`MAX_QUERIES` times. Every
generated statement passes the same read-only guard as the Ask flow
(``connector.validate``) before touching a data source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.connectors.base import Connector, ConnectorError, QueryResult
from app.models.connection import Connection
from app.models.user import User
from app.services.ai.base import ChatMessage, ChatTurn, ToolCall, ToolResult, ToolSpec
from app.services.ai.factory import get_ai_provider
from app.services.clarity.reader import load_clarity_context
from app.services.connections import load_connector
from app.services.prompt_store import ANALYSIS_PROMPT_KEY, get_prompt
from app.services.schema.cache import ensure_snapshot
from app.services.schema.introspect import SchemaData
from app.services.schema.select import select_schema
from app.services.sql_guard import SqlGuardError

MAX_QUERIES = 5
_MAX_RESULT_ROWS = 100
_MAX_RESULT_CHARS = 4000

_RUN_SQL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "connection_id": {
            "type": "integer",
            "description": "ID of the database connection to query (from the schema sections).",
        },
        "sql": {
            "type": "string",
            "description": "A single read-only SELECT statement in the connection's dialect.",
        },
        "purpose": {
            "type": "string",
            "description": "One short sentence: what this query is checking.",
        },
    },
    "required": ["connection_id", "sql"],
}


@dataclass
class AnalysisStep:
    """One ``run_sql`` attempt, successful or not (shown to the user)."""

    connection_id: int | None
    connection_name: str | None
    purpose: str | None
    sql: str
    row_count: int | None = None
    error: str | None = None


@dataclass
class AnalysisOutcome:
    answer: str
    steps: list[AnalysisStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Source:
    connection: Connection
    connector: Connector


def _serialize_result(result: QueryResult) -> str:
    """Compact JSON for the model; capped so results can't blow up the prompt."""
    payload = {
        "columns": [name for name, _type in result.columns],
        "rows": result.rows[:_MAX_RESULT_ROWS],
        "row_count": result.row_count,
        "truncated": result.truncated or result.row_count > _MAX_RESULT_ROWS,
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + '... (result truncated)"'
    return text


async def _build_system(
    session: AsyncSession,
    *,
    question: str,
    sources: dict[int, _Source],
    include_clarity: bool,
    warnings: list[str],
) -> str:
    prompt, _ = await get_prompt(session, ANALYSIS_PROMPT_KEY)
    parts: list[str] = [prompt]

    if include_clarity:
        clarity_context = await load_clarity_context(session)
        if clarity_context is None:
            warnings.append(
                "Clarity was selected but no Clarity data is stored yet; "
                "the answer cannot use Clarity metrics."
            )
        else:
            parts.append(clarity_context)

    settings = get_settings()
    if sources:
        per_source_budget = max(500, settings.schema_max_tokens // len(sources))
        for conn_id, source in sources.items():
            snapshot = await ensure_snapshot(session, conn_id, source.connector)
            schema_data = cast(SchemaData, snapshot.content_json)
            selected = select_schema(schema_data, question, per_source_budget)
            warnings.extend(selected.warnings)
            parts.append(
                f"Database connection id={conn_id} "
                f'name="{source.connection.name}" dialect={source.connector.label}:\n'
                + source.connector.schema_block(selected.text)
            )
    return "\n\n".join(parts)


async def _execute_tool_call(
    call: ToolCall, sources: dict[int, _Source], steps: list[AnalysisStep]
) -> ToolResult:
    raw_id = call.input.get("connection_id")
    sql = str(call.input.get("sql") or "")
    purpose = call.input.get("purpose")
    purpose_text = str(purpose) if purpose else None

    try:
        conn_id = int(cast(Any, raw_id))
    except (TypeError, ValueError):
        conn_id = -1
    source = sources.get(conn_id)
    if source is None:
        steps.append(
            AnalysisStep(
                connection_id=None,
                connection_name=None,
                purpose=purpose_text,
                sql=sql,
                error=f"Unknown connection_id {raw_id!r}.",
            )
        )
        return ToolResult(
            tool_call_id=call.id,
            content=(f"Unknown connection_id {raw_id!r}. Available ids: {sorted(sources)}."),
            is_error=True,
        )

    step = AnalysisStep(
        connection_id=conn_id,
        connection_name=source.connection.name,
        purpose=purpose_text,
        sql=sql,
    )
    steps.append(step)
    settings = get_settings()
    try:
        safe_sql = source.connector.validate(sql)
        step.sql = safe_sql
        result = await run_in_threadpool(
            source.connector.run, safe_sql, min(_MAX_RESULT_ROWS, settings.query_max_rows)
        )
    except SqlGuardError as exc:
        step.error = f"Rejected by the read-only guard: {exc}"
        return ToolResult(tool_call_id=call.id, content=step.error, is_error=True)
    except ConnectorError as exc:
        step.error = f"Query failed: {exc}"
        return ToolResult(tool_call_id=call.id, content=step.error, is_error=True)

    step.row_count = result.row_count
    return ToolResult(tool_call_id=call.id, content=_serialize_result(result))


async def run_analysis(
    session: AsyncSession,
    user: User,
    *,
    question: str,
    connection_ids: list[int],
    include_clarity: bool,
) -> AnalysisOutcome:
    """Run the agentic analysis loop and return the grounded answer."""
    warnings: list[str] = []
    sources: dict[int, _Source] = {}
    for conn_id in connection_ids:
        connection, connector = await load_connector(session, conn_id, user)
        sources[connection.id] = _Source(connection=connection, connector=connector)

    system = await _build_system(
        session,
        question=question,
        sources=sources,
        include_clarity=include_clarity,
        warnings=warnings,
    )
    tools = (
        [
            ToolSpec(
                name="run_sql",
                description=(
                    "Run one read-only SELECT against a listed database connection "
                    "and get its rows back as JSON."
                ),
                input_schema=_RUN_SQL_SCHEMA,
            )
        ]
        if sources
        else []
    )

    provider = get_ai_provider()
    messages: list[ChatMessage] = [ChatMessage(role="user", text=f"Question: {question}")]
    steps: list[AnalysisStep] = []
    queries_used = 0

    while True:
        turn: ChatTurn = await run_in_threadpool(
            provider.chat, system=system, messages=messages, tools=tools
        )
        if not turn.tool_calls:
            if turn.text:
                return AnalysisOutcome(answer=turn.text, steps=steps, warnings=warnings)
            break  # empty turn - force a text answer below

        messages.append(
            ChatMessage(role="assistant", text=turn.text, tool_calls=list(turn.tool_calls))
        )
        results: list[ToolResult] = []
        for call in turn.tool_calls:
            if queries_used >= MAX_QUERIES:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=f"Query limit reached ({MAX_QUERIES}). Answer with what you have.",
                        is_error=True,
                    )
                )
                continue
            queries_used += 1
            results.append(await _execute_tool_call(call, sources, steps))
        messages.append(ChatMessage(role="user", tool_results=results))

        if queries_used >= MAX_QUERIES:
            break

    messages.append(
        ChatMessage(
            role="user",
            text="Give your final answer now, based only on the data gathered so far.",
        )
    )
    turn = await run_in_threadpool(
        provider.chat, system=system, messages=messages, tools=tools, force_text=True
    )
    answer = turn.text or "The analysis could not produce an answer from the available data."
    return AnalysisOutcome(answer=answer, steps=steps, warnings=warnings)
