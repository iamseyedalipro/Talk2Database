"""Tests for the schema-browser response model.

The ``GET /api/schema`` handler validates the cached ``SchemaSnapshot.content_json``
(introspect-shaped) through :class:`DbSchema` and returns it. The risky part is the
``schema`` key, which is exposed via an alias because it shadows a Pydantic attribute,
so these tests pin the dict-in / JSON-out contract.
"""

from __future__ import annotations

from typing import Any

from app.schemas.schema import DbSchema


def _content_json() -> dict[str, Any]:
    """A snapshot ``content_json`` exactly as produced by ``introspect_userdata``."""
    return {
        "tables": [
            {
                "schema": "public",
                "name": "orders",
                "comment": "Customer orders",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False, "comment": None},
                    {"name": "customer_id", "type": "integer", "nullable": False, "comment": None},
                ],
                "primary_key": ["id"],
                "foreign_keys": [
                    {
                        "columns": ["customer_id"],
                        "ref_schema": "public",
                        "ref_table": "customers",
                        "ref_columns": ["id"],
                    }
                ],
            }
        ]
    }


def test_db_schema_parses_introspect_content_json() -> None:
    model = DbSchema.model_validate(_content_json())
    assert len(model.tables) == 1
    table = model.tables[0]
    assert table.schema_name == "public"
    assert table.name == "orders"
    assert [c.name for c in table.columns] == ["id", "customer_id"]
    assert table.primary_key == ["id"]
    assert table.foreign_keys[0].ref_table == "customers"


def test_db_schema_serializes_schema_key_with_alias() -> None:
    model = DbSchema.model_validate(_content_json())
    # FastAPI serializes the response by alias, so the wire shape must use "schema".
    dumped = model.model_dump(by_alias=True)
    assert dumped["tables"][0]["schema"] == "public"
    assert "schema_name" not in dumped["tables"][0]


def test_db_schema_handles_empty() -> None:
    model = DbSchema.model_validate({"tables": []})
    assert model.tables == []
