"""Tests for schema-grounded identifier verification of generated SQL."""

from __future__ import annotations

from app.services.schema.introspect import SchemaData
from app.services.sql_verify import build_correction_feedback, verify_identifiers


def _table(schema: str, name: str, columns: list[str]) -> dict:
    return {
        "schema": schema,
        "name": name,
        "comment": None,
        "columns": [
            {"name": c, "type": "text", "nullable": True, "comment": None} for c in columns
        ],
        "primary_key": [],
        "foreign_keys": [],
    }


SCHEMA: SchemaData = {
    "tables": [
        _table("public", "orders", ["id", "amount", "customer_id", "created_at"]),
        _table("public", "customers", ["id", "name"]),
        _table("sales", "targets", ["id", "quota"]),
    ]
}


def _verify(sql: str, dialect: str = "postgres"):
    return verify_identifiers(sql, SCHEMA, dialect)


# --- tables ----------------------------------------------------------------- #
def test_hallucinated_table_is_flagged() -> None:
    result = _verify("SELECT * FROM income")
    assert result.unknown_tables == ["income"]
    assert not result.ok


def test_known_tables_pass() -> None:
    assert _verify("SELECT id, amount FROM orders").ok


def test_qualified_schema_table() -> None:
    assert _verify("SELECT quota FROM sales.targets").ok
    assert _verify("SELECT * FROM public.orders").ok
    result = _verify("SELECT * FROM sales.nonexistent")
    assert result.unknown_tables == ["sales.nonexistent"]


def test_system_tables_whitelisted() -> None:
    assert _verify("SELECT table_name FROM information_schema.tables").ok
    assert _verify("SELECT relname FROM pg_catalog.pg_class").ok


def test_table_functions_and_values_pass() -> None:
    assert _verify("SELECT * FROM generate_series(1, 10)").ok
    assert _verify("SELECT 1").ok
    assert _verify("SELECT * FROM (VALUES (1), (2)) AS v(x)").ok


# --- columns ---------------------------------------------------------------- #
def test_hallucinated_column_is_flagged() -> None:
    result = _verify("SELECT amout FROM orders")
    assert result.unknown_columns == ["amout"]


def test_qualified_hallucinated_column_uses_table_name() -> None:
    result = _verify("SELECT o.bogus FROM orders o")
    assert result.unknown_columns == ["orders.bogus"]


def test_aliased_join_columns_pass() -> None:
    sql = """
    SELECT o.amount, c.name
    FROM orders o JOIN customers c ON c.id = o.customer_id
    """
    assert _verify(sql).ok


def test_select_alias_in_order_by_passes() -> None:
    sql = "SELECT sum(amount) AS total FROM orders GROUP BY 1 ORDER BY total"
    assert _verify(sql).ok


def test_function_argument_columns_are_checked() -> None:
    assert _verify("SELECT EXTRACT(year FROM created_at) FROM orders").ok
    result = _verify("SELECT EXTRACT(year FROM created_off) FROM orders")
    assert result.unknown_columns == ["created_off"]


def test_star_select_passes() -> None:
    assert _verify("SELECT * FROM orders").ok


def test_case_insensitive_identifiers() -> None:
    assert _verify("SELECT AMOUNT FROM Orders").ok


# --- CTEs / subqueries / set operations ------------------------------------- #
def test_cte_is_not_flagged_as_table() -> None:
    sql = "WITH t AS (SELECT amount FROM orders) SELECT amount FROM t"
    assert _verify(sql).ok


def test_recursive_cte_passes() -> None:
    sql = """
    WITH RECURSIVE r AS (
        SELECT id FROM customers
        UNION ALL
        SELECT r.id FROM r JOIN orders o ON o.customer_id = r.id
    )
    SELECT id FROM r
    """
    assert _verify(sql).ok


def test_cte_missing_column_is_flagged() -> None:
    sql = "WITH t AS (SELECT amount FROM orders) SELECT bogus FROM t"
    result = _verify(sql)
    assert result.unknown_columns == ["bogus"]


def test_star_cte_is_opaque() -> None:
    sql = "WITH t AS (SELECT * FROM orders) SELECT anything FROM t"
    assert _verify(sql).ok


def test_cte_inner_query_still_checked() -> None:
    sql = "WITH t AS (SELECT amount FROM income) SELECT amount FROM t"
    result = _verify(sql)
    assert result.unknown_tables == ["income"]


def test_correlated_subquery_passes() -> None:
    sql = """
    SELECT o.amount FROM orders o
    WHERE EXISTS (SELECT 1 FROM customers c WHERE c.id = o.customer_id)
    """
    assert _verify(sql).ok


def test_union_branches_are_both_checked() -> None:
    result = _verify("SELECT id FROM orders UNION SELECT id FROM income")
    assert result.unknown_tables == ["income"]


def test_derived_table_columns_checked() -> None:
    sql = "SELECT sub.amount FROM (SELECT amount FROM orders) sub"
    assert _verify(sql).ok
    result = _verify("SELECT sub.bogus FROM (SELECT amount FROM orders) sub")
    assert result.unknown_columns == ["sub.bogus"]


def test_duplicates_are_deduped() -> None:
    result = _verify("SELECT a.x FROM income a JOIN income b ON b.x = a.x")
    assert result.unknown_tables == ["income"]


# --- feedback --------------------------------------------------------------- #
def test_feedback_contains_suggestions_and_directory() -> None:
    result = _verify("SELECT amout FROM orderz")
    feedback = build_correction_feedback(result, SCHEMA)
    assert "orderz" in feedback
    assert "orders" in feedback  # close match suggestion
    assert "TABLES:" in feedback


def test_feedback_lists_real_columns_for_bad_column() -> None:
    result = _verify("SELECT o.amout FROM orders o")
    feedback = build_correction_feedback(result, SCHEMA)
    assert "orders.amout" in feedback
    assert "amount" in feedback
    assert "TABLE orders" in feedback
