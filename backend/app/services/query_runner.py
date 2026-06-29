"""Execute validated read-only SQL against the user-data database."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as dtime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.postgres import types as pg_types

from app.db.userdata import readonly_connection


@dataclass
class QueryResult:
    columns: list[tuple[str, str]]  # (name, type)
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int


def _type_name(oid: int) -> str:
    try:
        info = pg_types.get(oid)
    except Exception:
        return str(oid)
    return info.name if info is not None else str(oid)


def to_jsonable(value: Any) -> Any:
    """Convert a Postgres value into a JSON-serializable form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "\\x" + bytes(value).hex()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def run_select(sql: str, max_rows: int) -> QueryResult:
    """Run a SELECT and return up to ``max_rows`` rows (plus a truncation flag).

    The statement is assumed already validated by ``sql_guard``; execution still
    happens on a read-only role inside a read-only transaction with a timeout.
    """
    with readonly_connection() as conn, conn.cursor() as cur:
        start = time.monotonic()
        cur.execute(sql)
        description = cur.description or []
        columns = [(col.name, _type_name(col.type_code)) for col in description]
        fetched = cur.fetchmany(max_rows + 1)
        elapsed_ms = int((time.monotonic() - start) * 1000)

    truncated = len(fetched) > max_rows
    data = fetched[:max_rows]
    rows = [[to_jsonable(value) for value in row] for row in data]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=elapsed_ms,
    )
