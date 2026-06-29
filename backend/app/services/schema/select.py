"""Cost-aware schema selection.

When the full serialized schema fits within the token budget we send all of it
(ideal: it becomes a stable, cacheable prefix). When it does not, we send only
the tables most relevant to the question — plus their foreign-key neighbours and
a compact directory of every table name — so joins still resolve while the
prompt stays small. This directly bounds the per-question AI cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.schema.introspect import SchemaData, TableInfo
from app.services.schema.serialize import (
    estimate_tokens,
    serialize_schema,
    serialize_tables,
    table_directory,
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class SelectedSchema:
    """The schema text to send to the AI, plus any user-facing warnings."""

    text: str
    warnings: list[str] = field(default_factory=list)
    table_count_sent: int = 0
    table_count_total: int = 0


def _tokens(text: str) -> set[str]:
    return {tok for tok in _WORD_RE.findall(text.lower()) if len(tok) >= 3}


def _trigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return {cleaned[i : i + 3] for i in range(len(cleaned) - 2)}


def _table_text(table: TableInfo) -> str:
    parts = [table["name"], table["comment"] or ""]
    for column in table["columns"]:
        parts.append(column["name"])
        if column["comment"]:
            parts.append(column["comment"])
    return " ".join(parts)


def _score(table: TableInfo, q_tokens: set[str], q_trigrams: set[str]) -> tuple[float, float]:
    """Return ``(strong, total)`` relevance scores for a table.

    ``strong`` counts only direct token/name overlap with the question; ``total``
    adds a small fuzzy (trigram) component. Seeds are chosen from strong matches
    so a fuzzy near-miss never crowds out a real foreign-key neighbour.
    """
    name = table["name"].lower()
    t_tokens = _tokens(_table_text(table))
    strong = 3.0 * len(q_tokens & t_tokens) + 2.0 * sum(1 for qt in q_tokens if qt in name)
    total = strong + 0.1 * len(q_trigrams & _trigrams(name))
    return strong, total


def select_schema(schema: SchemaData, question: str, max_tokens: int) -> SelectedSchema:
    """Return the schema text to send for ``question``, bounded by ``max_tokens``."""
    tables = schema["tables"]
    total = len(tables)
    full_text = serialize_schema(schema)

    if total == 0 or estimate_tokens(full_text) <= max_tokens:
        return SelectedSchema(text=full_text, table_count_sent=total, table_count_total=total)

    q_tokens = _tokens(question)
    q_trigrams = _trigrams(question)
    by_name = {table["name"]: table for table in tables}

    scored = [(*_score(table, q_tokens, q_trigrams), table) for table in tables]
    scored.sort(key=lambda row: row[1], reverse=True)
    # Seeds are tables with a direct match. If nothing matches, fall back to the
    # single highest-ranked table so we still send something concrete.
    seeds = [table for strong, _total, table in scored if strong > 0] or [scored[0][2]]
    ranked = [table for _strong, _total, table in scored]

    directory = table_directory(schema)
    budget = max_tokens - estimate_tokens(directory)

    selected: dict[str, TableInfo] = {}

    def _try_add(table: TableInfo) -> bool:
        if table["name"] in selected:
            return True
        candidate = serialize_tables([*selected.values(), table])
        if estimate_tokens(candidate) <= budget or not selected:
            selected[table["name"]] = table
            return True
        return False

    # Add each seed together with its foreign-key neighbours, so joins resolve
    # before any leftover budget is spent on lower-relevance tables.
    for table in seeds:
        if not _try_add(table):
            break
        for fk in table["foreign_keys"]:
            neighbour = by_name.get(fk["ref_table"])
            if neighbour is not None:
                _try_add(neighbour)

    # Use any remaining budget for the next most relevant tables.
    for table in ranked:
        _try_add(table)

    chosen = [table for table in tables if table["name"] in selected]
    text = f"{directory}\n\n{serialize_tables(chosen)}"
    warning = (
        f"The schema has {total} tables, which exceeds the configured token budget. "
        f"Sent the {len(chosen)} tables most relevant to your question (with their related "
        f"tables). Mention a table by name if you need one that was not included."
    )
    return SelectedSchema(
        text=text,
        warnings=[warning],
        table_count_sent=len(chosen),
        table_count_total=total,
    )
