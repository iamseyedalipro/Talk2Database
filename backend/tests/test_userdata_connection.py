"""Regression test for the read-only connection's SET statements.

psycopg3 rejects server-side parameters inside ``SET`` commands, so the timeout
guards must be issued as rendered SQL literals (no ``%s``/``$1`` placeholder and
no parameters argument). This guards against the
``syntax error at or near "$1"`` regression.
"""

from __future__ import annotations

from types import SimpleNamespace

import app.db.userdata as userdata


class _FakeCursor:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, query: object, params: object = None) -> None:
        # SET statements are psycopg ``sql.Composed`` objects; render to text.
        rendered = query.as_string(None) if hasattr(query, "as_string") else str(query)
        self._calls.append((rendered, params))


class _FakeConnection:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self._calls = calls
        self.committed = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._calls)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def test_set_statements_use_literals_not_parameters(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    conn = _FakeConnection(calls)

    monkeypatch.setattr(
        userdata,
        "get_settings",
        lambda: SimpleNamespace(
            query_timeout_seconds=30,
            userdata_readonly_dsn="postgresql://user:pw@localhost:5432/db",
        ),
    )
    monkeypatch.setattr(userdata.psycopg, "connect", lambda *a, **k: conn)

    with userdata.readonly_connection() as yielded:
        assert yielded is conn

    assert conn.committed is True
    assert conn.closed is True

    set_calls = [(q, p) for q, p in calls if q.upper().startswith("SET STATEMENT_TIMEOUT")]
    idle_calls = [
        (q, p) for q, p in calls if q.upper().startswith("SET IDLE_IN_TRANSACTION_SESSION_TIMEOUT")
    ]
    assert set_calls, "statement_timeout was never set"
    assert idle_calls, "idle_in_transaction_session_timeout was never set"

    for query, params in set_calls + idle_calls:
        # No bound parameters and no placeholder — the value is inlined as a literal.
        assert params is None
        assert "%s" not in query
        assert "$1" not in query
        assert "30000" in query  # 30 seconds * 1000 ms
