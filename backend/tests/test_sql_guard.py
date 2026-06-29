"""Tests for the read-only SQL guard — the application-level safety layer."""

from __future__ import annotations

import pytest

from app.services.sql_guard import SqlGuardError, validate_select

VALID = [
    "SELECT 1",
    "select id, name from customers where id = 5",
    "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
    "SELECT a FROM t UNION SELECT b FROM u",
    "SELECT count(*) FROM customers GROUP BY region",
    "SELECT c.id, r.name FROM customers c JOIN regions r ON r.id = c.region_id LIMIT 10",
]

INVALID = [
    "",
    "DROP TABLE customers",
    "DELETE FROM customers",
    "UPDATE customers SET name = 'x'",
    "INSERT INTO customers (id) VALUES (1)",
    "TRUNCATE customers",
    "CREATE TABLE t (id int)",
    "ALTER TABLE t ADD COLUMN x int",
    "GRANT SELECT ON customers TO bob",
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE customers",
    "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
    "SELECT * INTO backup FROM customers",
    "SELECT * FROM customers FOR UPDATE",
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "COPY customers TO STDOUT",
    "VACUUM",
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_selects_pass(sql: str) -> None:
    normalized = validate_select(sql)
    assert normalized  # returns a non-empty, re-serialized statement
    assert normalized.lower().lstrip().startswith(("select", "with", "(")), normalized


@pytest.mark.parametrize("sql", INVALID)
def test_invalid_statements_are_rejected(sql: str) -> None:
    with pytest.raises(SqlGuardError):
        validate_select(sql)


def test_normalized_output_is_executable_form() -> None:
    # The returned text is re-serialized from the validated AST.
    out = validate_select("select   1   as   one")
    assert "1" in out and out.count(";") == 0
