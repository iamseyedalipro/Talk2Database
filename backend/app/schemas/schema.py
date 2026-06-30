"""Response models for the database-structure (schema browser) endpoint.

These mirror the ``SchemaData`` / ``TableInfo`` / ``ColumnInfo`` / ``ForeignKeyInfo``
TypedDicts produced by :mod:`app.services.schema.introspect` and stored verbatim in
``SchemaSnapshot.content_json``. Declaring them as Pydantic models gives the endpoint a
typed, validated contract in the OpenAPI schema.

The ``schema`` JSON key is exposed via an alias because ``schema`` shadows a Pydantic
``BaseModel`` attribute; internally the field is ``schema_name``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SchemaColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    comment: str | None = None


class SchemaForeignKey(BaseModel):
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]


class SchemaTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    name: str
    comment: str | None = None
    columns: list[SchemaColumn]
    primary_key: list[str]
    foreign_keys: list[SchemaForeignKey]


class DbSchema(BaseModel):
    tables: list[SchemaTable]
