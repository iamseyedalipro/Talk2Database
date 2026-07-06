"""Bounded distinct-value sampling for text columns.

Enum and CHECK columns get their allowed values from the catalog (see
``introspect``). Plain text columns whose domain is enforced only in application
code have no such metadata, so — when enabled — we probe a bounded sample of
rows for a *small* set of distinct values and attach them to the column. This is
the only place introspection reads row data; it stays cheap by capping both the
rows scanned and the number of distinct values kept.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.schema.introspect import SchemaData

# A column is worth sampling only if it looks like a short text/label column.
# ``char`` covers char/varchar/character varying; ``text`` covers text/*text.
_TEXTUAL_HINTS = ("char", "text")
_TEXTUAL_EXACT = frozenset({"citext", "name", "string"})


def is_textual(column_type: str) -> bool:
    """Whether a column type is a text-like type worth sampling for values."""
    lowered = column_type.lower()
    return lowered in _TEXTUAL_EXACT or any(hint in lowered for hint in _TEXTUAL_HINTS)


# ``sample(schema, table, column) -> distinct values`` or ``None`` when the
# column is unsuitable (too many distinct values, an error, or empty).
SampleFn = Callable[[str, str, str], list[str] | None]


def apply_sampled_values(schema: SchemaData, *, sample: SampleFn, enabled: bool) -> None:
    """Fill ``allowed_values`` for eligible text columns, in place.

    Skips columns that already have values (enum/CHECK), primary-key columns,
    and non-text columns. ``sample`` is a connector-provided, dialect-safe probe.
    """
    if not enabled:
        return
    for table in schema["tables"]:
        pk = set(table["primary_key"])
        for column in table["columns"]:
            if column["allowed_values"] is not None or column["name"] in pk:
                continue
            if not is_textual(column["type"]):
                continue
            values = sample(table["schema"], table["name"], column["name"])
            if values:
                # Sort for a deterministic snapshot fingerprint across refreshes.
                column["allowed_values"] = sorted(values)
