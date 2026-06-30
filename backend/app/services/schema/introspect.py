"""Introspect a SQL database into a structured, JSON-able schema.

Only structural metadata is read (table/column/type/PK/FK/comments) — never any
row data. Each connector calls the dialect-specific function here with an already
open, read-only connection cursor. The :class:`SchemaData` shape is shared across
every connector so serialization, fingerprinting and relevance trimming stay
source-agnostic.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class ColumnInfo(TypedDict):
    name: str
    type: str
    nullable: bool
    comment: str | None


class ForeignKeyInfo(TypedDict):
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]


class TableInfo(TypedDict):
    schema: str
    name: str
    comment: str | None
    columns: list[ColumnInfo]
    primary_key: list[str]
    foreign_keys: list[ForeignKeyInfo]


class SchemaData(TypedDict):
    tables: list[TableInfo]


class Cursor(Protocol):
    """Minimal DB-API cursor surface used by introspection."""

    def execute(self, query: str, params: Any = ...) -> Any: ...
    def fetchall(self) -> list[Any]: ...


_COLUMNS_SQL = """
SELECT
    c.table_schema,
    c.table_name,
    c.column_name,
    c.data_type,
    (c.is_nullable = 'YES')                         AS nullable,
    c.ordinal_position,
    col_description(pgc.oid, c.ordinal_position)    AS column_comment,
    obj_description(pgc.oid)                         AS table_comment
FROM information_schema.columns c
JOIN pg_namespace ns ON ns.nspname = c.table_schema
JOIN pg_class pgc ON pgc.relname = c.table_name AND pgc.relnamespace = ns.oid
WHERE c.table_schema = ANY(%(schemas)s)
ORDER BY c.table_schema, c.table_name, c.ordinal_position;
"""

_PRIMARY_KEY_SQL = """
SELECT tc.table_schema, tc.table_name, kcu.column_name, kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.constraint_schema = tc.constraint_schema
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = ANY(%(schemas)s)
ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position;
"""

_FOREIGN_KEY_SQL = """
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    kcu.column_name,
    kcu.ordinal_position,
    ccu.table_schema AS ref_schema,
    ccu.table_name   AS ref_table,
    ccu.column_name  AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.constraint_schema = tc.constraint_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.constraint_schema = tc.constraint_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = ANY(%(schemas)s)
ORDER BY tc.table_schema, tc.table_name, tc.constraint_name, kcu.ordinal_position;
"""


def introspect_postgres(
    cur: Cursor, schemas: list[str], allowlist: set[str]
) -> SchemaData:
    """Read the structural schema of a PostgreSQL database via ``cur``.

    Returns a deterministic, sorted structure (tables and columns ordered) so
    the serialized form and its fingerprint are stable across runs.
    """
    params: dict[str, Any] = {"schemas": schemas}

    cur.execute(_COLUMNS_SQL, params)
    column_rows = cur.fetchall()
    cur.execute(_PRIMARY_KEY_SQL, params)
    pk_rows = cur.fetchall()
    cur.execute(_FOREIGN_KEY_SQL, params)
    fk_rows = cur.fetchall()

    tables: dict[tuple[str, str], TableInfo] = {}

    for schema, table, column, data_type, nullable, _pos, col_comment, tbl_comment in column_rows:
        if allowlist and table not in allowlist:
            continue
        key = (schema, table)
        info = tables.get(key)
        if info is None:
            info = TableInfo(
                schema=schema,
                name=table,
                comment=tbl_comment,
                columns=[],
                primary_key=[],
                foreign_keys=[],
            )
            tables[key] = info
        info["columns"].append(
            ColumnInfo(name=column, type=data_type, nullable=nullable, comment=col_comment)
        )

    for schema, table, column, _pos in pk_rows:
        info = tables.get((schema, table))
        if info is not None:
            info["primary_key"].append(column)

    # Group multi-column foreign keys by constraint name.
    fk_acc: dict[tuple[str, str, str], ForeignKeyInfo] = {}
    for schema, table, constraint, column, _pos, ref_schema, ref_table, ref_column in fk_rows:
        if (schema, table) not in tables:
            continue
        acc_key = (schema, table, constraint)
        fk = fk_acc.get(acc_key)
        if fk is None:
            fk = ForeignKeyInfo(
                columns=[], ref_schema=ref_schema, ref_table=ref_table, ref_columns=[]
            )
            fk_acc[acc_key] = fk
        fk["columns"].append(column)
        fk["ref_columns"].append(ref_column)

    for (schema, table, _constraint), fk in fk_acc.items():
        tables[(schema, table)]["foreign_keys"].append(fk)

    return _finalize(tables)


def _finalize(tables: dict[tuple[str, str], TableInfo]) -> SchemaData:
    """Deterministically order tables, columns and foreign keys."""
    ordered = sorted(tables.values(), key=lambda t: (t["schema"], t["name"]))
    for table_info in ordered:
        table_info["foreign_keys"].sort(key=lambda f: (f["ref_table"], tuple(f["columns"])))
    return SchemaData(tables=ordered)


# --------------------------------------------------------------------------- #
# MySQL / MariaDB
# --------------------------------------------------------------------------- #
_MYSQL_COLUMNS_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE,
       (IS_NULLABLE = 'YES') AS nullable, ORDINAL_POSITION,
       NULLIF(COLUMN_COMMENT, '') AS column_comment
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = %(db)s
ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

_MYSQL_TABLES_SQL = """
SELECT TABLE_NAME, NULLIF(TABLE_COMMENT, '') AS table_comment
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %(db)s AND TABLE_TYPE = 'BASE TABLE';
"""

_MYSQL_PK_SQL = """
SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = %(db)s AND CONSTRAINT_NAME = 'PRIMARY'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

_MYSQL_FK_SQL = """
SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME, ORDINAL_POSITION,
       REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = %(db)s AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
"""


def introspect_mysql(cur: Cursor, database: str, allowlist: set[str]) -> SchemaData:
    """Read the structural schema of a MySQL/MariaDB database via ``cur``.

    In MySQL the database itself is the namespace, so ``TableInfo.schema`` is set
    to ``database`` to keep the shared shape consistent with PostgreSQL.
    """
    params: dict[str, Any] = {"db": database}

    cur.execute(_MYSQL_COLUMNS_SQL, params)
    column_rows = cur.fetchall()
    cur.execute(_MYSQL_TABLES_SQL, params)
    table_rows = cur.fetchall()
    cur.execute(_MYSQL_PK_SQL, params)
    pk_rows = cur.fetchall()
    cur.execute(_MYSQL_FK_SQL, params)
    fk_rows = cur.fetchall()

    comments = dict(table_rows)
    tables: dict[tuple[str, str], TableInfo] = {}

    for schema, table, column, data_type, nullable, _pos, col_comment in column_rows:
        if allowlist and table not in allowlist:
            continue
        key = (schema, table)
        info = tables.get(key)
        if info is None:
            info = TableInfo(
                schema=schema,
                name=table,
                comment=comments.get(table),
                columns=[],
                primary_key=[],
                foreign_keys=[],
            )
            tables[key] = info
        info["columns"].append(
            ColumnInfo(name=column, type=data_type, nullable=bool(nullable), comment=col_comment)
        )

    for table, column, _pos in pk_rows:
        info = tables.get((database, table))
        if info is not None:
            info["primary_key"].append(column)

    fk_acc: dict[tuple[str, str], ForeignKeyInfo] = {}
    for table, constraint, column, _pos, ref_schema, ref_table, ref_column in fk_rows:
        if (database, table) not in tables:
            continue
        acc_key = (table, constraint)
        fk = fk_acc.get(acc_key)
        if fk is None:
            fk = ForeignKeyInfo(
                columns=[], ref_schema=ref_schema, ref_table=ref_table, ref_columns=[]
            )
            fk_acc[acc_key] = fk
        fk["columns"].append(column)
        fk["ref_columns"].append(ref_column)

    for (table, _constraint), fk in fk_acc.items():
        tables[(database, table)]["foreign_keys"].append(fk)

    return _finalize(tables)
