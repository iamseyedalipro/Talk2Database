"""Serialize introspected schema into a compact, deterministic text block.

The text is what we send to the AI. It is sorted and stable so it works well as
a cacheable prompt prefix, and a fingerprint over the structure lets us detect
"nothing changed" and skip rewriting a snapshot.
"""

from __future__ import annotations

import hashlib
import json

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
        comment = f"  -- {column['comment']}" if column["comment"] else ""
        lines.append(f"  {column['name']} {column['type']}{flags}{comment}")

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


def fingerprint(schema: SchemaData) -> str:
    """Stable SHA-256 over the canonical structure (order-independent of dict keys)."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
