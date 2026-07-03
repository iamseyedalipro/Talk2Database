"""Tests for EXPLAIN (FORMAT JSON) parsing for Postgres and MySQL."""

from __future__ import annotations

import json

from app.services.explain import parse_mysql_explain, parse_postgres_explain

_PG_PLAN = [
    {
        "Plan": {
            "Node Type": "Aggregate",
            "Total Cost": 23.45,
            "Plan Rows": 12,
            "Plans": [{"Node Type": "Seq Scan", "Total Cost": 18.1, "Plan Rows": 410}],
        }
    }
]

_MYSQL_PLAN = {
    "query_block": {
        "select_id": 1,
        "cost_info": {"query_cost": "1.99"},
        "table": {
            "table_name": "orders",
            "rows_examined_per_scan": 410,
            "rows_produced_per_join": 42,
        },
    }
}


def test_parse_postgres_explain_reads_top_node() -> None:
    # Accepts the already-parsed list (psycopg decodes json automatically)...
    assert parse_postgres_explain(_PG_PLAN) == (23.45, 12)
    # ...and a JSON string.
    assert parse_postgres_explain(json.dumps(_PG_PLAN)) == (23.45, 12)


def test_parse_mysql_explain_reads_cost_and_rows() -> None:
    cost, rows = parse_mysql_explain(json.dumps(_MYSQL_PLAN))
    assert cost == 1.99
    assert rows == 42  # prefers rows_produced_per_join


def test_parse_mysql_explain_nested_ordering() -> None:
    plan = {
        "query_block": {
            "cost_info": {"query_cost": "9.0"},
            "ordering_operation": {"table": {"rows_produced_per_join": 7}},
        }
    }
    assert parse_mysql_explain(plan) == (9.0, 7)


def test_parsers_tolerate_unexpected_shapes() -> None:
    assert parse_postgres_explain("not json") == (None, None)
    assert parse_postgres_explain([{}]) == (None, None)
    assert parse_mysql_explain({"unexpected": True}) == (None, None)
