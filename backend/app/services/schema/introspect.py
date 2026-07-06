"""Introspect a SQL database into a structured, JSON-able schema.

Only structural metadata is read (table/column/type/PK/FK/comments) — never any
row data. Each connector calls the dialect-specific function here with an already
open, read-only connection cursor. The :class:`SchemaData` shape is shared across
every connector so serialization, fingerprinting and relevance trimming stay
source-agnostic.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, TypedDict


class ColumnInfo(TypedDict):
    name: str
    type: str
    nullable: bool
    comment: str | None
    # Known allowed values for the column (enum labels, CHECK IN-list, or a
    # bounded distinct sample). ``None`` means "unknown / unconstrained".
    allowed_values: list[str] | None


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


# Matches the "column IN (…)" / "column = ANY (…)" head of a CHECK clause across
# dialects: the column may be bare, quoted ("col" / `col`), or wrapped/cast such
# as ``(status)::text``. Case-insensitive so MySQL's lowercase ``in`` also hits.
_CHECK_COLUMN_RE = re.compile(
    r"""[(\s]*                     # optional leading paren/space
        [`"]?(?P<col>[A-Za-z_][A-Za-z0-9_]*)[`"]?   # the column name
        \)?                       # optional closing paren from ``(col)``
        (?:::[\w ]+)?             # optional ::cast
        \s*                        # spaces
        (?:=\s*ANY|IN)\b          # the membership operator
    """,
    re.IGNORECASE | re.VERBOSE,
)

# String literals inside a CHECK/enum definition. Handles doubled '' escapes and
# ignores any charset prefix (MySQL renders values as ``_utf8mb4'value'``).
_STRING_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")

# The membership operator, used to reject multi-column checks (where collecting
# every literal would mis-attribute values to a single column).
_MEMBERSHIP_RE = re.compile(r"(?:=\s*ANY|\bIN)\b", re.IGNORECASE)


def _string_literals(text: str) -> list[str]:
    """All single-quoted string literals in ``text``, de-duplicated, in order."""
    seen: dict[str, None] = {}
    for raw in _STRING_LITERAL_RE.findall(text):
        seen.setdefault(raw.replace("''", "'"), None)
    return list(seen)


def _parse_check_values(definition: str) -> tuple[str, list[str]] | None:
    """Extract ``(column, [values])`` from a simple membership CHECK clause.

    Handles the common shapes across PostgreSQL and MySQL:
    ``col IN ('a','b')``, ``col = ANY (ARRAY['a','b'])`` and their quoted/cast
    variants. Returns ``None`` for anything not confidently a single-column
    string membership check (biased to false-negatives).
    """
    # Only a single-column membership check is safe to attribute values to.
    if len(_MEMBERSHIP_RE.findall(definition)) != 1:
        return None
    match = _CHECK_COLUMN_RE.search(definition)
    if match is None:
        return None
    values = _string_literals(definition)
    if not values:
        return None
    return match.group("col"), values


def _parse_enum_type(column_type: str) -> list[str] | None:
    """Extract labels from a MySQL ``enum('a','b',…)`` column type, else ``None``."""
    lowered = column_type.strip().lower()
    if not lowered.startswith("enum("):
        return None
    values = _string_literals(column_type)
    return values or None


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

_ENUM_SQL = """
SELECT
    n.nspname   AS table_schema,
    c.relname   AS table_name,
    a.attname   AS column_name,
    e.enumlabel AS label
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c      ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace n  ON n.oid = c.relnamespace
JOIN pg_catalog.pg_type t       ON t.oid = a.atttypid
JOIN pg_catalog.pg_enum e       ON e.enumtypid = t.oid
WHERE n.nspname::text = ANY(%(schemas)s)
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY n.nspname, c.relname, a.attname, e.enumsortorder;
"""

_CHECK_SQL = """
SELECT
    n.nspname                                   AS table_schema,
    c.relname                                   AS table_name,
    pg_catalog.pg_get_constraintdef(con.oid)    AS definition
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c      ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n  ON n.oid = c.relnamespace
WHERE n.nspname::text = ANY(%(schemas)s)
  AND con.contype = 'c';
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
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fcol(attnum, position)
    ON fcol.position = col.position
JOIN pg_catalog.pg_attribute a  ON a.attrelid = c.oid  AND a.attnum = col.attnum
JOIN pg_catalog.pg_attribute fa ON fa.attrelid = fc.oid AND fa.attnum = fcol.attnum
WHERE n.nspname::text = ANY(%(schemas)s)
  AND con.contype = 'f'
ORDER BY n.nspname, c.relname, con.conname, col.position;
"""


def introspect_postgres(cur: Cursor, schemas: list[str] | None, allowlist: set[str]) -> SchemaData:
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
    cur.execute(_ENUM_SQL, params)
    enum_rows = cur.fetchall()
    cur.execute(_CHECK_SQL, params)
    check_rows = cur.fetchall()

    # (schema, table, column) -> allowed values, from native enums and then
    # CHECK constraints (enums win; a column is rarely both).
    values: dict[tuple[str, str, str], list[str]] = {}
    for schema, table, column, label in enum_rows:
        values.setdefault((schema, table, column), []).append(label)
    for schema, table, definition in check_rows:
        parsed = _parse_check_values(definition)
        if parsed is None:
            continue
        column, allowed = parsed
        values.setdefault((schema, table, column), allowed)

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
            ColumnInfo(
                name=column,
                type=data_type,
                nullable=nullable,
                comment=col_comment,
                allowed_values=values.get((schema, table, column)),
            )
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

# CHECK constraints (MySQL 8.0.16+ / MariaDB 10.2+). information_schema.
# CHECK_CONSTRAINTS lacks the table name on MySQL, so join TABLE_CONSTRAINTS.
_MYSQL_CHECK_SQL = """
SELECT tc.TABLE_NAME, cc.CHECK_CLAUSE
FROM information_schema.CHECK_CONSTRAINTS cc
JOIN information_schema.TABLE_CONSTRAINTS tc
  ON tc.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA
 AND tc.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
WHERE cc.CONSTRAINT_SCHEMA = %(db)s;
"""


def _mysql_check_values(cur: Cursor, database: str) -> dict[tuple[str, str], list[str]]:
    """Best-effort ``(table, column) -> values`` from MySQL CHECK constraints.

    Returns an empty map on any error (older servers without CHECK_CONSTRAINTS).
    """
    result: dict[tuple[str, str], list[str]] = {}
    try:
        cur.execute(_MYSQL_CHECK_SQL, {"db": database})
        rows = cur.fetchall()
    except Exception:
        return result
    for table, clause in rows:
        parsed = _parse_check_values(clause or "")
        if parsed is not None:
            result.setdefault((table, parsed[0]), parsed[1])
    return result


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
    check_values = _mysql_check_values(cur, database)

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
        # Native ENUM values are embedded in COLUMN_TYPE; otherwise fall back to
        # a CHECK constraint on this column.
        allowed = _parse_enum_type(data_type) or check_values.get((table, column))
        info["columns"].append(
            ColumnInfo(
                name=column,
                type=data_type,
                nullable=bool(nullable),
                comment=col_comment,
                allowed_values=allowed,
            )
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
