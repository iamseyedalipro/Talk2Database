"""Tests for schema serialization, fingerprinting and cost-aware selection."""

from __future__ import annotations

from typing import Any

from app.services.schema.select import select_schema
from app.services.schema.serialize import fingerprint, serialize_schema, serialize_table


def _col(name: str, type_: str = "integer", nullable: bool = True) -> dict[str, Any]:
    return {"name": name, "type": type_, "nullable": nullable, "comment": None}


def _table(
    name: str,
    columns: list[dict[str, Any]],
    pk: list[str] | None = None,
    fks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "public",
        "name": name,
        "comment": None,
        "columns": columns,
        "primary_key": pk or [],
        "foreign_keys": fks or [],
    }


def _fk(columns: list[str], ref_table: str, ref_columns: list[str]) -> dict[str, Any]:
    return {
        "columns": columns,
        "ref_schema": "public",
        "ref_table": ref_table,
        "ref_columns": ref_columns,
    }


def test_serialize_table_includes_pk_notnull_and_fk() -> None:
    table = _table(
        "orders",
        [_col("id"), _col("customer_id", nullable=False)],
        pk=["id"],
        fks=[_fk(["customer_id"], "customers", ["id"])],
    )
    text = serialize_table(table)
    assert "TABLE orders (PK: id)" in text
    assert "customer_id integer NOT NULL" in text
    assert "FK (customer_id) -> customers(id)" in text


def test_serialize_empty_schema() -> None:
    assert "empty" in serialize_schema({"tables": []}).lower()


def test_fingerprint_is_stable_and_sensitive() -> None:
    schema_a = {"tables": [_table("t", [_col("id")], pk=["id"])]}
    schema_b = {"tables": [_table("t", [_col("id")], pk=["id"])]}
    schema_c = {"tables": [_table("t", [_col("id"), _col("extra")], pk=["id"])]}
    assert fingerprint(schema_a) == fingerprint(schema_b)
    assert fingerprint(schema_a) != fingerprint(schema_c)


def test_small_schema_sent_in_full() -> None:
    schema = {"tables": [_table("customers", [_col("id"), _col("email", "text")], pk=["id"])]}
    result = select_schema(schema, "how many customers?", max_tokens=10_000)
    assert result.warnings == []
    assert result.table_count_sent == 1
    assert "customers" in result.text


def _wide_table(name: str, fks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    columns = [_col(f"a_descriptive_column_name_number_{i}", "text") for i in range(15)]
    return _table(name, columns, pk=["a_descriptive_column_name_number_0"], fks=fks)


def test_large_schema_is_trimmed_to_relevant_tables_with_fk_neighbours() -> None:
    tables = [_wide_table(f"unrelated_table_{i}") for i in range(8)]
    tables.append(_wide_table("orders", fks=[_fk(["cust"], "customers", ["id"])]))
    tables.append(_wide_table("customers"))
    schema = {"tables": tables}

    full = serialize_schema(schema)
    # Sanity: the full schema is genuinely large.
    assert len(full) > 4000

    result = select_schema(schema, "show me the latest orders", max_tokens=450)

    assert result.warnings, "expected a trimming warning"
    assert result.table_count_total == 10
    assert result.table_count_sent < 10
    # The relevant table and its FK neighbour are included...
    assert "TABLE orders" in result.text
    assert "TABLE customers" in result.text
    # ...and a compact directory of every table name is always present.
    assert "TABLES:" in result.text
    assert "unrelated_table_0" in result.text  # listed in the directory
