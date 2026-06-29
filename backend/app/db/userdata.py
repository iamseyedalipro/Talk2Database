"""Connection factory for the user-data database.

Every connection opened here authenticates as the **read-only** role and is
further pinned to a read-only transaction with a statement timeout. This is the
*only* path the request-serving API uses to touch the user's data; restores and
syncs use a separate admin DSN that never enters the request path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from app.config import get_settings


@contextmanager
def readonly_connection() -> Iterator[psycopg.Connection]:
    """Yield a hardened, read-only connection to the user-data database.

    The connection is opened as the SELECT-only role, marked
    ``default_transaction_read_only``, and given a ``statement_timeout`` so a
    runaway AI query cannot hang the panel. Even if every other guard failed,
    the role itself lacks write/DDL privileges.
    """
    settings = get_settings()
    timeout_ms = max(1, settings.query_timeout_seconds) * 1000
    conn = psycopg.connect(settings.userdata_readonly_dsn, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute("SET statement_timeout = %s", (timeout_ms,))
            cur.execute("SET idle_in_transaction_session_timeout = %s", (timeout_ms,))
        conn.commit()
        yield conn
    finally:
        conn.close()


def userdata_reachable() -> bool:
    """Return ``True`` if the user-data database accepts a read-only connection."""
    try:
        with readonly_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
