"""Serialize introspected schema into a compact, deterministic text block.

The text is what we send to the AI. It is sorted and stable so it works well as
a cacheable prompt prefix, and a fingerprint over the structure lets us detect
"nothing changed" and skip rewriting a snapshot.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.schema.introspect import SchemaData, TableInfo


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 characters per token)."""
    return (len(text) + 3) // 4


def _qualified(table: TableInfo) -> str:
    schema = table["schema"]
    return table["name"] if schema == "public" else f"{schema}.{table['name']}"


def serialize_table(table: TableInfo) -> str:
    """Render a single table as a deterministic text block."""
    lines: list[str] = []
    header = f"TABLE {_qualified(table)}"
    if table["primary_key"]:
        header += f" (PK: {', '.join(table['primary_key'])})"
    if table["comment"]:
        header += f"  -- {table['comment']}"
    lines.append(header)

    for column in table["columns"]:
        flags = "" if column["nullable"] else " NOT NULL"
        annotations: list[str] = []
        if column["comment"]:
            annotations.append(column["comment"])
        allowed = column.get("allowed_values")
        if allowed:
            annotations.append("allowed values: " + ", ".join(allowed))
        note = f"  -- {'; '.join(annotations)}" if annotations else ""
        lines.append(f"  {column['name']} {column['type']}{flags}{note}")

    for fk in table["foreign_keys"]:
        ref = (
            fk["ref_table"]
            if fk["ref_schema"] == "public"
            else (f"{fk['ref_schema']}.{fk['ref_table']}")
        )
        lines.append(f"  FK ({', '.join(fk['columns'])}) -> {ref}({', '.join(fk['ref_columns'])})")
    return "\n".join(lines)


def serialize_tables(tables: list[TableInfo]) -> str:
    """Render multiple tables, separated by blank lines."""
    return "\n\n".join(serialize_table(table) for table in tables)


def serialize_schema(schema: SchemaData) -> str:
    """Render the full schema."""
    if not schema["tables"]:
        return "(the database is currently empty — no tables have been imported yet)"
    return serialize_tables(schema["tables"])


def table_directory(schema: SchemaData) -> str:
    """A one-line-per-table listing of names only (cheap orientation for the AI)."""
    names = [_qualified(table) for table in schema["tables"]]
    return "TABLES: " + ", ".join(names)


def table_to_json(table: TableInfo) -> dict[str, Any]:
    """Render a single table as a JSON-serializable dict with a fixed key order.

    Empty/absent annotations are omitted so the payload stays compact; key order
    is fixed so the output is deterministic and works as a cacheable prefix.
    """
    columns: list[dict[str, Any]] = []
    for column in table["columns"]:
        col: dict[str, Any] = {"name": column["name"], "type": column["type"]}
        if column["nullable"]:
            col["nullable"] = True
        if column["comment"]:
            col["comment"] = column["comment"]
        allowed = column.get("allowed_values")
        if allowed:
            col["allowed_values"] = list(allowed)
        columns.append(col)

    out: dict[str, Any] = {"table": _qualified(table)}
    if table["comment"]:
        out["comment"] = table["comment"]
    if table["primary_key"]:
        out["primary_key"] = list(table["primary_key"])
    out["columns"] = columns
    if table["foreign_keys"]:
        out["foreign_keys"] = [
            {
                "columns": list(fk["columns"]),
                "references": (
                    fk["ref_table"]
                    if fk["ref_schema"] == "public"
                    else f"{fk['ref_schema']}.{fk['ref_table']}"
                ),
                "ref_columns": list(fk["ref_columns"]),
            }
            for fk in table["foreign_keys"]
        ]
    return out


def serialize_tables_json(tables: list[TableInfo]) -> str:
    """Render multiple tables as one compact, deterministic JSON array."""
    return json.dumps([table_to_json(t) for t in tables], separators=(",", ":"), default=str)


def table_directory_json(schema: SchemaData) -> str:
    """The table-name directory as compact JSON (names only, snapshot order)."""
    names = [_qualified(table) for table in schema["tables"]]
    return json.dumps({"tables": names}, separators=(",", ":"))


def fingerprint(schema: SchemaData) -> str:
    """Stable SHA-256 over the canonical structure (order-independent of dict keys)."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
