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


# Use pg_catalog throughout instead of information_schema so that any database
# user who can connect sees tables — information_schema filters by privilege.
_USER_SCHEMAS_SQL = """
SELECT nspname
FROM pg_catalog.pg_namespace
WHERE nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
  AND nspname NOT LIKE 'pg_%'
ORDER BY nspname;
"""

_COLUMNS_SQL = """
SELECT
    n.nspname                                                   AS table_schema,
    c.relname                                                   AS table_name,
    a.attname                                                   AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod)            AS data_type,
    NOT a.attnotnull                                            AS nullable,
    a.attnum                                                    AS ordinal_position,
    pg_catalog.col_description(c.oid, a.attnum)                AS column_comment,
    pg_catalog.obj_description(c.oid, 'pg_class')              AS table_comment
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c      ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n  ON n.oid = c.relnamespace
WHERE n.nspname::text = ANY(%(schemas)s)
  AND c.relkind IN ('r', 'p', 'v', 'f', 'm')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY n.nspname, c.relname, a.attnum;
"""

_PRIMARY_KEY_SQL = """
SELECT
    n.nspname                   AS table_schema,
    c.relname                   AS table_name,
    a.attname                   AS column_name,
    col.position
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c      ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n  ON n.oid = c.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS col(attnum, position) ON TRUE
JOIN pg_catalog.pg_attribute a  ON a.attrelid = c.oid AND a.attnum = col.attnum
WHERE n.nspname::text = ANY(%(schemas)s)
  AND con.contype = 'p'
ORDER BY n.nspname, c.relname, col.position;
"""

_FOREIGN_KEY_SQL = """
SELECT
    n.nspname                   AS table_schema,
    c.relname                   AS table_name,
    con.conname                 AS constraint_name,
    a.attname                   AS column_name,
    col.position,
    fn.nspname                  AS ref_schema,
    fc.relname                  AS ref_table,
    fa.attname                  AS ref_column
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c      ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n  ON n.oid = c.relnamespace
JOIN pg_catalog.pg_class fc     ON fc.oid = con.confrelid
JOIN pg_catalog.pg_namespace fn ON fn.oid = fc.relnamespace
JOIN LATERAL unnest(con.conkey)  WITH ORDINALITY AS col(attnum, position)  ON TRUE
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fcol(attnum, position) ON fcol.position = col.position
JOIN pg_catalog.pg_attribute a  ON a.attrelid = c.oid  AND a.attnum = col.attnum
JOIN pg_catalog.pg_attribute fa ON fa.attrelid = fc.oid AND fa.attnum = fcol.attnum
WHERE n.nspname::text = ANY(%(schemas)s)
  AND con.contype = 'f'
ORDER BY n.nspname, c.relname, con.conname, col.position;
"""


def introspect_postgres(
    cur: Cursor, schemas: list[str] | None, allowlist: set[str]
) -> SchemaData:
    """Read the structural schema of a PostgreSQL database via ``cur``.

    Returns a deterministic, sorted structure (tables and columns ordered) so
    the serialized form and its fingerprint are stable across runs.

    When ``schemas`` is ``None`` or empty, all non-system schemas are discovered
    automatically so tables outside the ``public`` schema are found.
    """
    if not schemas:
        cur.execute(_USER_SCHEMAS_SQL)
        schemas = [row[0] for row in cur.fetchall()] or ["public"]

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
