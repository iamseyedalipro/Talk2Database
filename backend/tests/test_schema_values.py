"""Tests for allowed-value discovery: enum/CHECK extraction, sampling, rendering."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.connectors import ConnectionConfig, get_connector
from app.services.schema.introspect import (
    _parse_check_values,
    _parse_enum_type,
    introspect_mysql,
    introspect_postgres,
)
from app.services.schema.sample import apply_sampled_values, is_textual
from app.services.schema.serialize import serialize_table


class FakeCursor:
    """Return canned rows based on a marker substring found in the executed SQL.

    ``routes`` is an ordered list of ``(marker, rows)``; the first marker that
    appears in the query wins. Non-string queries (psycopg ``Composed``) are
    routed via the ``composed`` fallback.
    """

    def __init__(self, routes: list[tuple[str, list[Any]]], composed: list[Any] | None = None):
        self._routes = routes
        self._composed = composed or []
        self._rows: list[Any] = []

    def execute(self, query: Any, params: Any = None) -> None:
        if not isinstance(query, str):
            self._rows = self._composed
            return
        for marker, rows in self._routes:
            if marker in query:
                self._rows = rows
                return
        self._rows = []

    def fetchall(self) -> list[Any]:
        return self._rows


# --------------------------------------------------------------------------- #
# CHECK / enum parsing
# --------------------------------------------------------------------------- #
def test_parse_check_values_pg_any_array() -> None:
    definition = "CHECK (status = ANY (ARRAY['successful'::text, 'failed'::text, 'pending'::text]))"
    assert _parse_check_values(definition) == ("status", ["successful", "failed", "pending"])


def test_parse_check_values_pg_in_and_cast() -> None:
    definition = "CHECK (((status)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[])))"  # noqa: E501
    assert _parse_check_values(definition) == ("status", ["a", "b"])
    assert _parse_check_values("CHECK (kind IN ('x', 'y'))") == ("kind", ["x", "y"])


def test_parse_check_values_mysql_backtick_charset() -> None:
    clause = "(`status` in (_utf8mb4'successful',_utf8mb4'failed',_utf8mb4'pending'))"
    assert _parse_check_values(clause) == ("status", ["successful", "failed", "pending"])


def test_parse_check_values_rejects_non_membership() -> None:
    assert _parse_check_values("CHECK (amount > 0)") is None
    assert _parse_check_values("CHECK (created_at < now())") is None


def test_parse_check_values_rejects_multi_column() -> None:
    # Two membership operators -> we can't safely attribute values to one column.
    definition = "CHECK (region IN ('EU', 'US') AND status IN ('a', 'b'))"
    assert _parse_check_values(definition) is None


def test_parse_enum_type_mysql() -> None:
    assert _parse_enum_type("enum('successful','failed','pending')") == [
        "successful",
        "failed",
        "pending",
    ]
    assert _parse_enum_type("varchar(255)") is None


# --------------------------------------------------------------------------- #
# Introspection wires values onto columns
# --------------------------------------------------------------------------- #
def test_introspect_postgres_attaches_enum_and_check() -> None:
    columns = [
        ("public", "payments", "id", "integer", False, 1, None, None),
        ("public", "payments", "status", "payment_status", False, 2, None, None),
        ("public", "payments", "channel", "text", True, 3, None, None),
    ]
    enums = [
        ("public", "payments", "status", "successful"),
        ("public", "payments", "status", "failed"),
        ("public", "payments", "status", "pending"),
    ]
    checks = [("public", "payments", "CHECK (channel IN ('web', 'app'))")]
    cur = FakeCursor(
        [
            ("format_type", columns),
            ("contype = 'p'", []),
            ("contype = 'f'", []),
            ("pg_enum", enums),
            ("pg_get_constraintdef", checks),
        ]
    )
    schema = introspect_postgres(cur, ["public"], set())
    cols = {c["name"]: c for c in schema["tables"][0]["columns"]}
    assert cols["status"]["allowed_values"] == ["successful", "failed", "pending"]
    assert cols["channel"]["allowed_values"] == ["web", "app"]
    assert cols["id"]["allowed_values"] is None


def test_introspect_mysql_enum_and_check() -> None:
    columns = [
        ("shop", "payments", "id", "int", False, 1, None),
        ("shop", "payments", "status", "enum('successful','failed','pending')", False, 2, None),
        ("shop", "payments", "channel", "varchar(20)", True, 3, None),
    ]
    tables = [("payments", None)]
    checks = [("payments", "(`channel` in (_utf8mb4'web',_utf8mb4'app'))")]
    cur = FakeCursor(
        [
            ("information_schema.COLUMNS", columns),
            ("information_schema.TABLES", tables),
            ("'PRIMARY'", []),
            ("REFERENCED_TABLE_NAME IS NOT NULL", []),
            ("CHECK_CONSTRAINTS", checks),
        ]
    )
    schema = introspect_mysql(cur, "shop", set())
    cols = {c["name"]: c for c in schema["tables"][0]["columns"]}
    assert cols["status"]["allowed_values"] == ["successful", "failed", "pending"]
    assert cols["channel"]["allowed_values"] == ["web", "app"]


# --------------------------------------------------------------------------- #
# Serialization rendering
# --------------------------------------------------------------------------- #
def test_serialize_table_renders_allowed_values() -> None:
    table: dict[str, Any] = {
        "schema": "public",
        "name": "payments",
        "comment": None,
        "primary_key": [],
        "foreign_keys": [],
        "columns": [
            {
                "name": "status",
                "type": "varchar",
                "nullable": False,
                "comment": "payment state",
                "allowed_values": ["successful", "failed", "pending"],
            }
        ],
    }
    text = serialize_table(table)
    assert (
        "status varchar NOT NULL  -- payment state; allowed values: successful, failed, pending"
        in text
    )


# --------------------------------------------------------------------------- #
# Sampling helper + connector cap logic
# --------------------------------------------------------------------------- #
def test_is_textual() -> None:
    assert is_textual("varchar(20)")
    assert is_textual("character varying")
    assert is_textual("text")
    assert is_textual("citext")
    assert not is_textual("integer")
    assert not is_textual("timestamp with time zone")


def test_apply_sampled_values_selects_eligible_columns() -> None:
    schema: dict[str, Any] = {
        "tables": [
            {
                "schema": "public",
                "name": "t",
                "comment": None,
                "primary_key": ["id"],
                "foreign_keys": [],
                "columns": [
                    {
                        "name": "id",
                        "type": "text",
                        "nullable": False,
                        "comment": None,
                        "allowed_values": None,
                    },
                    {
                        "name": "kind",
                        "type": "varchar(10)",
                        "nullable": True,
                        "comment": None,
                        "allowed_values": None,
                    },
                    {
                        "name": "amount",
                        "type": "integer",
                        "nullable": True,
                        "comment": None,
                        "allowed_values": None,
                    },
                    {
                        "name": "state",
                        "type": "text",
                        "nullable": True,
                        "comment": None,
                        "allowed_values": ["a"],
                    },
                ],
            }
        ]
    }
    sampled: list[str] = []

    def fake_sample(s: str, t: str, c: str) -> list[str] | None:
        sampled.append(c)
        return ["z", "a"]

    apply_sampled_values(schema, sample=fake_sample, enabled=True)  # type: ignore[arg-type]
    cols = {c["name"]: c for c in schema["tables"][0]["columns"]}
    # id skipped (PK), amount skipped (non-text), state skipped (already has values).
    assert sampled == ["kind"]
    # Values are sorted for a stable fingerprint.
    assert cols["kind"]["allowed_values"] == ["a", "z"]


def test_apply_sampled_values_disabled_is_noop() -> None:
    schema: dict[str, Any] = {
        "tables": [
            {
                "schema": "public",
                "name": "t",
                "comment": None,
                "primary_key": [],
                "foreign_keys": [],
                "columns": [
                    {
                        "name": "kind",
                        "type": "text",
                        "nullable": True,
                        "comment": None,
                        "allowed_values": None,
                    }
                ],
            }
        ]
    }
    apply_sampled_values(schema, sample=lambda s, t, c: ["x"], enabled=False)  # type: ignore[arg-type]
    assert schema["tables"][0]["columns"][0]["allowed_values"] is None


def test_mysql_sample_values_caps_high_cardinality() -> None:
    connector = get_connector(
        ConnectionConfig(type="mysql", host="h", port=1, database="d", username="u", password="p")
    )
    settings = Settings(schema_sample_max_values=3, schema_sample_scan_limit=100)

    low = FakeCursor([], composed=[])
    low._routes = [("SELECT DISTINCT", [("web",), ("app",)])]
    assert connector._sample_values(low, "d", "t", "channel", settings) == ["web", "app"]  # type: ignore[attr-defined]

    high_rows = [("a",), ("b",), ("c",), ("d",)]
    high = FakeCursor([("SELECT DISTINCT", high_rows)])
    assert connector._sample_values(high, "d", "t", "channel", settings) is None  # type: ignore[attr-defined]


def test_postgres_sample_values_uses_savepoint_and_caps() -> None:
    connector = get_connector(
        ConnectionConfig(
            type="postgres", host="h", port=1, database="d", username="u", password="p"
        )
    )
    settings = Settings(schema_sample_max_values=3, schema_sample_scan_limit=100)

    # The DISTINCT query is a psycopg Composed (non-str) -> routed via ``composed``;
    # SAVEPOINT/RELEASE are plain strings and are ignored by the fake.
    low = FakeCursor([], composed=[("web",), ("app",)])
    assert connector._sample_values(low, "public", "t", "channel", settings) == ["web", "app"]  # type: ignore[attr-defined]

    high = FakeCursor([], composed=[("a",), ("b",), ("c",), ("d",)])
    assert connector._sample_values(high, "public", "t", "channel", settings) is None  # type: ignore[attr-defined]
