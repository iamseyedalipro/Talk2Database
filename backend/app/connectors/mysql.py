"""MySQL / MariaDB connector — live, read-only connections.

MariaDB is wire-compatible with MySQL, so both share this implementation and the
sqlglot ``mysql`` dialect; only the human-facing label differs.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

import pymysql
from pymysql.constants import FIELD_TYPE

from app.config import get_settings
from app.connectors.base import (
    ConnectionConfig,
    ConnectorError,
    ConnectorQueryError,
    QueryResult,
    to_jsonable,
)
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.schema.introspect import SchemaData, introspect_mysql
from app.services.sql_guard import validate_select

_CSV_BATCH = 1000

# Reverse map of MySQL protocol field type codes -> readable names.
_TYPE_NAMES: dict[int, str] = {
    value: name.lower()
    for name, value in vars(FIELD_TYPE).items()
    if not name.startswith("_") and isinstance(value, int)
}


def _type_name(type_code: int) -> str:
    return _TYPE_NAMES.get(type_code, str(type_code))


class MySQLConnector:
    """Connect to the user's MySQL/MariaDB database and query it read-only."""

    dialect = "mysql"

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self.type = config.type  # "mysql" or "mariadb"
        self._label = "MariaDB" if config.type == "mariadb" else "MySQL"
        self.label = self._label
        settings = get_settings()
        self._allowlist: set[str] = set(
            config.options.get("tables") or settings.schema_table_allowlist
        )
        self._timeout_s = max(1, settings.query_timeout_seconds)

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        c = self._config
        try:
            conn = pymysql.connect(
                host=c.host,
                port=c.port,
                user=c.username,
                password=c.password,
                database=c.database,
                connect_timeout=10,
                read_timeout=self._timeout_s + 5,
                autocommit=True,
                charset="utf8mb4",
            )
        except pymysql.Error as exc:
            raise ConnectorError(str(exc)) from exc
        try:
            with conn.cursor() as cur:
                # Best-effort read-only + timeouts. Not all of these exist on
                # every server/version, so failures are tolerated.
                for stmt in (
                    "SET SESSION TRANSACTION READ ONLY",
                    f"SET SESSION max_execution_time = {self._timeout_s * 1000}",
                    f"SET SESSION max_statement_time = {self._timeout_s}",
                ):
                    with suppress(pymysql.Error):
                        cur.execute(stmt)
            yield conn
        finally:
            conn.close()

    def introspect(self) -> SchemaData:
        with self._connect() as conn, conn.cursor() as cur:
            return introspect_mysql(cur, self._config.database, self._allowlist)

    def validate(self, query: str) -> str:
        return validate_select(query, dialect=self.dialect)

    def run(self, query: str, max_rows: int) -> QueryResult:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                start = time.monotonic()
                cur.execute(query)
                description = cur.description or []
                columns = [(col[0], _type_name(col[1])) for col in description]
                fetched = list(cur.fetchmany(max_rows + 1))
                elapsed_ms = int((time.monotonic() - start) * 1000)
        except pymysql.Error as exc:
            raise ConnectorQueryError(str(exc)) from exc

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

    def stream_csv(self, query: str, max_rows: int) -> Iterator[str]:
        import csv
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush() -> str:
            chunk = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            return chunk

        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(query)
                writer.writerow([col[0] for col in (cur.description or [])])
                yield flush()
                remaining = max_rows
                while remaining > 0:
                    batch = cur.fetchmany(min(_CSV_BATCH, remaining))
                    if not batch:
                        break
                    for row in batch:
                        writer.writerow([to_jsonable(value) for value in row])
                    remaining -= len(batch)
                    yield flush()
        except pymysql.Error as exc:
            raise ConnectorQueryError(str(exc)) from exc

    def reachable(self) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True

    def system_prompt(self) -> str:
        return build_system_prompt(self._label)

    def schema_block(self, schema_text: str) -> str:
        return build_schema_block(schema_text, self._label)
