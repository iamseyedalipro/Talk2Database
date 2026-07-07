"""Two-phase, on-demand table-detail discovery for SQL generation.

Instead of pre-selecting tables with a lexical scorer (:mod:`select`), we show
the model only the table-name *directory* first, then let it request the columns
of the tables it actually needs via a ``get_table_details`` tool. It reasons
semantically — aided by the business glossary — so a question like "how much we
sell week by week" pulls in the payments table that a keyword scorer would drop.

The loop is bounded (rounds, table count, token budget) and always degrades
safely: if it gathers nothing (the model answered in prose) or the provider
errors, we fall back to :func:`select_schema`. The result is a pre-rendered
schema block plus token usage, consumed exactly like a :class:`SelectedSchema`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.config import Settings
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
from app.services.schema.introspect import SchemaData, TableInfo
from app.services.schema.select import select_schema
from app.services.schema.serialize import (
    _qualified,
    estimate_tokens,
    serialize_schema,
    serialize_tables,
    table_directory,
)

logger = logging.getLogger(__name__)

_TOOL_NAME = "get_table_details"

_GET_TABLE_DETAILS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "table_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Exact table names copied from the TABLES directory whose full "
                "column detail you need to write the SQL."
            ),
        }
    },
    "required": ["table_names"],
}

_DISCOVERY_INSTRUCTIONS = (
    "Before writing any SQL, decide which tables you need. The database's tables "
    f"are listed by name only below. Call `{_TOOL_NAME}` with the exact names whose "
    "columns you need; you may call it again after seeing the details if you "
    "discover you need related tables (e.g. to resolve a join). When you have "
    "enough detail to write the query, reply with a brief plain-text confirmation "
    "and stop calling the tool. Do NOT write SQL yet."
)


@dataclass
class DiscoveredSchema:
    """The schema text to send to the AI, plus warnings and discovery-loop usage.

    Mirrors :class:`app.services.schema.select.SelectedSchema` (so the ask router
    consumes both symmetrically) and adds ``usage`` for the extra provider calls.
    """

    text: str
    warnings: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    table_count_sent: int = 0
    table_count_total: int = 0


def _build_system_prompt(ask_system_prompt: str, schema: SchemaData, glossary_text: str) -> str:
    """Discovery system prompt: ask rules + instructions + directory + glossary.

    The directory/glossary go last so the whole block is a stable, cacheable
    prefix across rounds (only ``messages`` grow between iterations).
    """
    parts = [ask_system_prompt, _DISCOVERY_INSTRUCTIONS, table_directory(schema)]
    if glossary_text:
        parts.append(glossary_text)
    return "\n\n".join(parts)


def _lookup(schema: SchemaData) -> dict[str, TableInfo]:
    """Map each table by both its bare name and its qualified form.

    ``table_directory`` renders ``schema.name`` for non-public schemas, so the
    model may echo either the bare or the qualified name back to us.
    """
    by_name: dict[str, TableInfo] = {}
    for table in schema["tables"]:
        by_name[table["name"]] = table
        by_name[_qualified(table)] = table
    return by_name


def _execute_details_call(
    call: ToolCall,
    by_name: dict[str, TableInfo],
    expanded: dict[str, TableInfo],
    render: Callable[[list[TableInfo]], str] = serialize_tables,
) -> ToolResult:
    """Render detail for the requested tables; record them in ``expanded``.

    Unknown names are reported (never invented). If *nothing* resolves, the
    result is an error so the model retries with names from the directory.
    ``render`` picks the detail format (text here; JSON in the analysis loop).
    """
    raw = call.input.get("table_names")
    names = [n for n in raw if isinstance(n, str)] if isinstance(raw, list) else []

    known: list[TableInfo] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for name in names:
        table = by_name.get(name) or by_name.get(name.strip())
        if table is None:
            unknown.append(name)
            continue
        key = _qualified(table)
        if key in seen:
            continue
        seen.add(key)
        known.append(table)
        expanded[key] = table

    valid = sorted({_qualified(t) for t in by_name.values()})
    if not known:
        return ToolResult(
            tool_call_id=call.id,
            content=f"None of {unknown!r} exist. Valid table names: {', '.join(valid)}",
            is_error=True,
        )

    detail = render(known)
    if unknown:
        detail += (
            f"\n\nUnrecognized (ignored): {', '.join(unknown)}. Valid names: {', '.join(valid)}"
        )
    return ToolResult(tool_call_id=call.id, content=detail)


def _fallback(
    schema: SchemaData, question: str, settings: Settings, usage: TokenUsage, reason: str
) -> DiscoveredSchema:
    """Degrade to the lexical selector, preserving its warnings and our usage."""
    selected = select_schema(schema, question, settings.schema_max_tokens)
    warnings = [reason, *selected.warnings]
    return DiscoveredSchema(
        text=selected.text,
        warnings=warnings,
        usage=usage,
        table_count_sent=selected.table_count_sent,
        table_count_total=selected.table_count_total,
    )


async def discover_schema(
    *,
    provider: LLMProvider,
    schema: SchemaData,
    question: str,
    ask_system_prompt: str,
    glossary_text: str,
    settings: Settings,
    emit: ProgressEmitter = noop_emit,
) -> DiscoveredSchema:
    """Let the model pick which tables' details to send, then render them.

    Returns the schema block (directory + detail for the chosen tables), any
    guardrail warnings, and the token usage of the discovery provider calls.
    """
    tables = schema["tables"]
    total = len(tables)
    if total == 0:
        return DiscoveredSchema(text=serialize_schema(schema))

    system = _build_system_prompt(ask_system_prompt, schema, glossary_text)
    by_name = _lookup(schema)
    tools = [
        ToolSpec(
            name=_TOOL_NAME,
            description="Get the full column/FK detail for specific tables by name.",
            input_schema=_GET_TABLE_DETAILS_SCHEMA,
        )
    ]
    directory = table_directory(schema)
    messages: list[ToolChatMessage] = [ToolChatMessage(role="user", text=f"Question: {question}")]
    expanded: dict[str, TableInfo] = {}
    usage = TokenUsage()
    warnings: list[str] = []

    await emit(
        {
            "type": "tables_directory",
            "count": total,
            "tables": [_qualified(t) for t in tables],
        }
    )

    for round_no in range(1, max(1, settings.ask_discovery_max_rounds) + 1):
        try:
            turn: ChatTurn = await run_in_threadpool(
                provider.chat, system=system, messages=messages, tools=tools
            )
        except AIProviderError as exc:
            logger.warning("Schema discovery failed; falling back to select_schema: %s", exc)
            return _fallback(
                schema,
                question,
                settings,
                usage,
                "Table discovery was unavailable; selected tables by keyword relevance instead.",
            )
        usage += turn.usage

        if not turn.tool_calls:
            # The model signalled it has enough detail (or answered in prose).
            break

        messages.append(
            ToolChatMessage(role="assistant", text=turn.text, tool_calls=list(turn.tool_calls))
        )
        results: list[ToolResult] = []
        for call in turn.tool_calls:
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
            results.append(_execute_details_call(call, by_name, expanded))
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
                f"Reached the table limit ({settings.ask_discovery_max_tables}); generating with "
                "the tables gathered so far. Mention a table by name if one is missing."
            )
            break
        if estimate_tokens(serialize_tables(list(expanded.values()))) > settings.schema_max_tokens:
            warnings.append(
                "The requested table details exceeded the token budget; generating with the "
                "tables gathered so far."
            )
            break
    else:
        warnings.append(
            f"Reached the discovery round limit ({settings.ask_discovery_max_rounds}); generating "
            "with the tables gathered so far."
        )

    if not expanded:
        return _fallback(
            schema,
            question,
            settings,
            usage,
            "The model requested no table details; selected tables by keyword relevance instead.",
        )

    # Render chosen tables in snapshot order (deterministic / cacheable).
    keys = {_qualified(t) for t in expanded.values()}
    chosen = [t for t in tables if _qualified(t) in keys]
    text = f"{directory}\n\n{serialize_tables(chosen)}"
    return DiscoveredSchema(
        text=text,
        warnings=warnings,
        usage=usage,
        table_count_sent=len(chosen),
        table_count_total=total,
    )
