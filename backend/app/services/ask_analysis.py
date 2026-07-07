"""The Ask analysis loop: agentic schema + data investigation before SQL.

Runs when the admin has turned on "Ask analysis mode". Like the discovery loop
(:mod:`app.services.schema.discover`) the model starts from a table-name
directory (JSON) and requests table details on demand — but it may also run
small, row-capped read-only SELECTs against the user's database and see the
sampled rows, so the final SQL is grounded in how the data actually looks.
Every exploratory statement passes the same read-only guard as Ask/Execute
(``connector.validate``) and runs inside the connector's read-only transaction
with its statement timeout; the row cap is admin-configurable.

The gathered directory, table details, and query findings are rendered into a
schema block consumed by ``generate_with_verification`` exactly like a
:class:`DiscoveredSchema`, so the final SQL still goes through structured
output, the guard, and identifier verification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.connectors.base import Connector, ConnectorError, QueryResult
from app.services.ai.base import (
    AIProviderError,
    ChatTurn,
    LLMProvider,
    TokenUsage,
    ToolCall,
    ToolChatMessage,
    ToolResult,
    ToolSpec,
)
from app.services.progress import ProgressEmitter, noop_emit
from app.services.prompt_store import ASK_ANALYSIS_PROMPT_KEY, get_prompt
from app.services.schema.discover import (
    _GET_TABLE_DETAILS_SCHEMA,
    _execute_details_call,
    _lookup,
)
from app.services.schema.introspect import SchemaData, TableInfo
from app.services.schema.select import select_schema
from app.services.schema.serialize import (
    _qualified,
    estimate_tokens,
    serialize_tables_json,
    table_directory_json,
)
from app.services.sql_guard import SqlGuardError

logger = logging.getLogger(__name__)

_DETAILS_TOOL = "get_table_details"
_QUERY_TOOL = "run_exploratory_query"

_PREVIEW_ROWS = 5  # rows shown in the UI activity feed (the model gets row_cap)
_MAX_RESULT_CHARS = 4000  # cap on the JSON fed back to the model per query

_RUN_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "description": (
                "A single read-only SELECT in the connection's dialect, with a LIMIT. "
                "Rows are capped server-side regardless."
            ),
        },
        "purpose": {
            "type": "string",
            "description": "One short sentence: what this query is checking.",
        },
    },
    "required": ["sql"],
}


@dataclass
class AnalysisExploration:
    """What the loop gathered, shaped like ``DiscoveredSchema`` for the caller."""

    text: str
    warnings: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    table_count_sent: int = 0
    table_count_total: int = 0


def _result_payload(result: QueryResult, row_cap: int) -> dict[str, Any]:
    return {
        "columns": [name for name, _type in result.columns],
        "rows": result.rows[:row_cap],
        "row_count": result.row_count,
        "truncated": result.truncated or result.row_count > row_cap,
    }


def _serialize_result(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, separators=(",", ":"), default=str)
    if len(text) > _MAX_RESULT_CHARS:
        text = text[:_MAX_RESULT_CHARS] + '... (result truncated)"'
    return text


def _render_output(
    directory_json: str, chosen: list[TableInfo], findings: list[dict[str, Any]]
) -> str:
    parts = [
        "TABLE DIRECTORY (JSON):\n" + directory_json,
        "TABLE DETAILS (JSON):\n" + serialize_tables_json(chosen),
    ]
    if findings:
        parts.append(
            "EXPLORATION FINDINGS (JSON) — results of read-only queries already "
            "run against this database while investigating the question:\n"
            + json.dumps(findings, separators=(",", ":"), default=str)
        )
    return "\n\n".join(parts)


async def _execute_query_call(
    call: ToolCall,
    *,
    connector: Connector,
    row_cap: int,
    round_no: int,
    findings: list[dict[str, Any]],
    emit: ProgressEmitter,
) -> ToolResult:
    sql = str(call.input.get("sql") or "")
    purpose = call.input.get("purpose")
    purpose_text = str(purpose) if purpose else None
    await emit(
        {"type": "exploratory_query", "round": round_no, "sql": sql, "purpose": purpose_text}
    )

    try:
        safe_sql = connector.validate(sql)
        result = await run_in_threadpool(connector.run, safe_sql, row_cap)
    except SqlGuardError as exc:
        error = f"Rejected by the read-only guard: {exc}"
        findings.append({"sql": sql, "purpose": purpose_text, "error": error})
        await emit({"type": "query_result", "sql": sql, "error": error})
        return ToolResult(tool_call_id=call.id, content=error, is_error=True)
    except ConnectorError as exc:
        error = f"Query failed: {exc}"
        findings.append({"sql": sql, "purpose": purpose_text, "error": error})
        await emit({"type": "query_result", "sql": sql, "error": error})
        return ToolResult(tool_call_id=call.id, content=error, is_error=True)

    payload = _result_payload(result, row_cap)
    findings.append({"sql": safe_sql, "purpose": purpose_text, "result": payload})
    await emit(
        {
            "type": "query_result",
            "sql": safe_sql,
            "columns": payload["columns"],
            "rows": payload["rows"][:_PREVIEW_ROWS],
            "row_count": payload["row_count"],
            "truncated": payload["truncated"],
            "error": None,
        }
    )
    return ToolResult(tool_call_id=call.id, content=_serialize_result(payload))


def _fallback(
    schema: SchemaData,
    question: str,
    settings: Settings,
    usage: TokenUsage,
    findings: list[dict[str, Any]],
    reason: str,
) -> AnalysisExploration:
    """Degrade to the lexical selector, keeping any findings already gathered."""
    selected = select_schema(schema, question, settings.schema_max_tokens)
    text = selected.text
    if findings:
        text += (
            "\n\nEXPLORATION FINDINGS (JSON) — results of read-only queries already "
            "run against this database while investigating the question:\n"
            + json.dumps(findings, separators=(",", ":"), default=str)
        )
    return AnalysisExploration(
        text=text,
        warnings=[reason, *selected.warnings],
        usage=usage,
        table_count_sent=selected.table_count_sent,
        table_count_total=selected.table_count_total,
    )


async def run_ask_analysis_loop(
    session: AsyncSession,
    *,
    provider: LLMProvider,
    connector: Connector,
    schema: SchemaData,
    question: str,
    ask_system_prompt: str,
    glossary_text: str,
    settings: Settings,
    row_cap: int,
    emit: ProgressEmitter = noop_emit,
) -> AnalysisExploration:
    """Investigate the schema and data, then render what was learned.

    Returns the schema block (JSON directory + JSON detail for the chosen
    tables + exploration findings), warnings, and the loop's token usage.
    """
    tables = schema["tables"]
    total = len(tables)
    directory_json = table_directory_json(schema)

    # Cache-stable prefix: instructions + directory + glossary go in the system
    # prompt; only ``messages`` grow between rounds.
    loop_prompt, _ = await get_prompt(session, ASK_ANALYSIS_PROMPT_KEY)
    parts = [ask_system_prompt, loop_prompt, "TABLE DIRECTORY (JSON):\n" + directory_json]
    if glossary_text:
        parts.append(glossary_text)
    system = "\n\n".join(parts)

    by_name = _lookup(schema)
    tools = [
        ToolSpec(
            name=_DETAILS_TOOL,
            description=(
                "Get the full column/key/relationship detail for specific tables by name, as JSON."
            ),
            input_schema=_GET_TABLE_DETAILS_SCHEMA,
        ),
        ToolSpec(
            name=_QUERY_TOOL,
            description=(
                "Run one small read-only SELECT against the database and get a "
                "row-capped JSON sample back. Use it to check value formats, "
                "ranges, and join keys before writing the final SQL."
            ),
            input_schema=_RUN_QUERY_SCHEMA,
        ),
    ]
    messages: list[ToolChatMessage] = [ToolChatMessage(role="user", text=f"Question: {question}")]
    expanded: dict[str, TableInfo] = {}
    findings: list[dict[str, Any]] = []
    usage = TokenUsage()
    warnings: list[str] = []
    queries_used = 0

    await emit(
        {"type": "tables_directory", "count": total, "tables": [_qualified(t) for t in tables]}
    )

    for round_no in range(1, max(1, settings.ask_analysis_max_rounds) + 1):
        try:
            turn: ChatTurn = await run_in_threadpool(
                provider.chat, system=system, messages=messages, tools=tools
            )
        except AIProviderError as exc:
            logger.warning("Ask analysis loop failed; falling back to select_schema: %s", exc)
            return _fallback(
                schema,
                question,
                settings,
                usage,
                findings,
                "The analysis investigation was unavailable; selected tables by "
                "keyword relevance instead.",
            )
        usage += turn.usage

        if turn.text and turn.text.strip():
            await emit({"type": "assistant_note", "text": turn.text.strip()})

        if not turn.tool_calls:
            break  # the model signalled it understands the data well enough

        messages.append(
            ToolChatMessage(role="assistant", text=turn.text, tool_calls=list(turn.tool_calls))
        )
        results: list[ToolResult] = []
        for call in turn.tool_calls:
            if call.name == _QUERY_TOOL:
                if queries_used >= settings.ask_analysis_max_queries:
                    results.append(
                        ToolResult(
                            tool_call_id=call.id,
                            content=(
                                f"Query limit reached ({settings.ask_analysis_max_queries}). "
                                "Proceed with what you have."
                            ),
                            is_error=True,
                        )
                    )
                    continue
                queries_used += 1
                results.append(
                    await _execute_query_call(
                        call,
                        connector=connector,
                        row_cap=row_cap,
                        round_no=round_no,
                        findings=findings,
                        emit=emit,
                    )
                )
                continue

            if call.name != _DETAILS_TOOL:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=f"Unknown tool '{call.name}'.",
                        is_error=True,
                    )
                )
                continue

            raw_names = call.input.get("table_names")
            requested = (
                [n for n in raw_names if isinstance(n, str)] if isinstance(raw_names, list) else []
            )
            await emit({"type": "tables_requested", "round": round_no, "table_names": requested})
            if len(expanded) >= settings.ask_discovery_max_tables:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=(
                            f"Table limit reached ({settings.ask_discovery_max_tables}). "
                            "Proceed with the tables already provided."
                        ),
                        is_error=True,
                    )
                )
                continue
            before = set(expanded)
            results.append(
                _execute_details_call(call, by_name, expanded, render=serialize_tables_json)
            )
            unknown = [n for n in requested if (by_name.get(n) or by_name.get(n.strip())) is None]
            await emit(
                {
                    "type": "table_details_sent",
                    "round": round_no,
                    "table_names": sorted(set(expanded) - before),
                    "unknown": unknown,
                }
            )
        messages.append(ToolChatMessage(role="user", tool_results=results))

        if len(expanded) >= settings.ask_discovery_max_tables:
            warnings.append(
                f"Reached the table limit ({settings.ask_discovery_max_tables}); generating "
                "with the tables gathered so far. Mention a table by name if one is missing."
            )
            break
        if estimate_tokens(serialize_tables_json(list(expanded.values()))) > (
            settings.schema_max_tokens
        ):
            warnings.append(
                "The requested table details exceeded the token budget; generating with "
                "the tables gathered so far."
            )
            break
    else:
        warnings.append(
            f"Reached the analysis round limit ({settings.ask_analysis_max_rounds}); "
            "generating with the tables gathered so far."
        )

    if not expanded:
        return _fallback(
            schema,
            question,
            settings,
            usage,
            findings,
            "The analysis loop requested no table details; selected tables by "
            "keyword relevance instead.",
        )

    # Render chosen tables in snapshot order (deterministic / cacheable).
    keys = {_qualified(t) for t in expanded.values()}
    chosen = [t for t in tables if _qualified(t) in keys]
    return AnalysisExploration(
        text=_render_output(directory_json, chosen, findings),
        warnings=warnings,
        usage=usage,
        table_count_sent=len(chosen),
        table_count_total=total,
    )
