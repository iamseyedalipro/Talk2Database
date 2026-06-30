"""PostgreSQL connector — live, read-only connections to a user's database."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.postgres import types as pg_types

from app.config import get_settings
from app.connectors.base import (
    ConnectionConfig,
    ConnectorQueryError,
    QueryResult,
    to_jsonable,
)
from app.services.ai.prompts import build_schema_block, build_system_prompt
from app.services.schema.introspect import SchemaData, introspect_postgres
from app.services.sql_guard import validate_select

_LABEL = "PostgreSQL"
_CSV_BATCH = 1000


def _type_name(oid: int) -> str:
    try:
        info = pg_types.get(oid)
    except Exception:
        return str(oid)
    return info.name if info is not None else str(oid)


class PostgresConnector:
    """Connect to the user's PostgreSQL database and query it read-only."""

    type = "postgres"
    dialect = "postgres"

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        settings = get_settings()
        self._schemas: list[str] = config.options.get("schemas") or settings.schema_namespaces
        self._allowlist: set[str] = set(
            config.options.get("tables") or settings.schema_table_allowlist
        )
        self._timeout_ms = max(1, settings.query_timeout_seconds) * 1000

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        """Yield a hardened, read-only connection.

        We do not own the user's database, so this is best-effort defence: a
        read-only transaction plus statement timeouts. The primary guarantees are
        the SQL guard and (recommended) a read-only database user.
        """
        c = self._config
        conn = psycopg.connect(
            host=c.host,
            port=c.port,
            dbname=c.database,
            user=c.username,
            password=c.password,
            autocommit=False,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SET default_transaction_read_only = on")
                cur.execute(sql.SQL("SET statement_timeout = {}").format(self._timeout_ms))
                cur.execute(
                    sql.SQL("SET idle_in_transaction_session_timeout = {}").format(self._timeout_ms)
                )
            conn.commit()
            yield conn
        finally:
            conn.close()

    def introspect(self) -> SchemaData:
        with self._connect() as conn, conn.cursor() as cur:
            return introspect_postgres(cur, self._schemas, self._allowlist)

    def validate(self, query: str) -> str:
        return validate_select(query, dialect=self.dialect)

    def run(self, query: str, max_rows: int) -> QueryResult:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                start = time.monotonic()
                cur.execute(query)
                description = cur.description or []
                columns = [(col.name, _type_name(col.type_code)) for col in description]
                fetched = cur.fetchmany(max_rows + 1)
                elapsed_ms = int((time.monotonic() - start) * 1000)
        except psycopg.Error as exc:
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
                writer.writerow([col.name for col in (cur.description or [])])
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
        except psycopg.Error as exc:
            raise ConnectorQueryError(str(exc)) from exc

    def reachable(self) -> bool:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception:
            return False

    def system_prompt(self) -> str:
        return build_system_prompt(_LABEL)

    def schema_block(self, schema_text: str) -> str:
        return build_schema_block(schema_text, _LABEL)
