"""Read-only SQL validation — the application-level half of defence in depth.

This module guarantees that a statement is a **single, read-only SELECT** before
it is ever sent to the database. It is paired with a hard guarantee at the
database layer (the ``t2db_readonly`` role cannot write or run DDL), so even a
parser bypass cannot mutate data. Keeping both layers means a weakness in either
one is not, by itself, exploitable.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


class SqlGuardError(ValueError):
    """Raised when a statement is not a single read-only SELECT."""


def _classes(*names: str) -> tuple[type[exp.Expression], ...]:
    """Resolve sqlglot expression classes by name, tolerating version drift."""
    resolved = [getattr(exp, name, None) for name in names]
    return tuple(c for c in resolved if isinstance(c, type))


# Only these may appear as the top-level statement.
_ALLOWED_ROOT = _classes("Select", "Union", "Except", "Intersect")

# These must not appear anywhere in the tree (including inside CTEs/subqueries).
_FORBIDDEN = _classes(
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Truncate",
    "Command",  # generic / unparsed commands: VACUUM, CALL, DO, ...
    "Set",
    "Use",
    "Grant",
    "Revoke",
    "Copy",
    "Into",  # SELECT ... INTO new_table  (creates a table)
    "Lock",  # SELECT ... FOR UPDATE/SHARE (write intent)
)

# Functions that can read the filesystem, sleep, or reach other systems.
# The set is dialect-aware: each entry holds the names that are dangerous for
# that dialect. The shared ``_COMMON`` names are blocked everywhere.
_COMMON_DANGEROUS = frozenset({"copy", "sleep", "load_file"})

_DANGEROUS_BY_DIALECT: dict[str, frozenset[str]] = {
    "postgres": frozenset(
        {
            "pg_read_file",
            "pg_read_binary_file",
            "pg_ls_dir",
            "pg_stat_file",
            "pg_sleep",
            "pg_sleep_for",
            "pg_sleep_until",
            "lo_import",
            "lo_export",
            "lo_get",
            "lo_put",
            "dblink",
            "dblink_exec",
            "dblink_connect",
        }
    ),
    # MySQL / MariaDB share a dialect/grammar in sqlglot ("mysql").
    "mysql": frozenset(
        {
            "load_file",
            "sleep",
            "benchmark",
            "get_lock",
            "release_lock",
        }
    ),
}


def _dangerous_functions(dialect: str) -> frozenset[str]:
    return _COMMON_DANGEROUS | _DANGEROUS_BY_DIALECT.get(dialect, frozenset())


def validate_select(sql: str, dialect: str = "postgres") -> str:
    """Validate ``sql`` and return a normalized, safe-to-execute statement.

    Returns the statement re-serialized from the parsed AST (in ``dialect``), so
    the text that is executed is exactly the text that was validated.

    Args:
        sql: The candidate statement.
        dialect: The sqlglot dialect to parse/serialize with (e.g. ``postgres``,
            ``mysql``). Non-SQL sources (e.g. Prometheus/PromQL) do their own
            validation and must not call this function.

    Raises:
        SqlGuardError: if the input is not a single read-only ``SELECT``.
    """
    stripped = sql.strip()
    if not stripped:
        raise SqlGuardError("empty statement")

    try:
        statements = [s for s in sqlglot.parse(stripped, read=dialect) if s is not None]
    except Exception as exc:
        raise SqlGuardError(f"could not parse SQL: {exc}") from exc

    if len(statements) == 0:
        raise SqlGuardError("no statement found")
    if len(statements) > 1:
        raise SqlGuardError("only a single statement is allowed")

    statement = statements[0]

    if not isinstance(statement, _ALLOWED_ROOT):
        raise SqlGuardError(
            f"only read-only SELECT queries are allowed (got {type(statement).__name__})"
        )

    for forbidden in _FORBIDDEN:
        node = statement.find(forbidden)
        if node is not None:
            raise SqlGuardError(f"statement contains a forbidden operation: {type(node).__name__}")

    dangerous = _dangerous_functions(dialect)
    for func in statement.find_all(exp.Func):
        name = (func.sql_name() or "").lower()  # type: ignore[no-untyped-call]
        if name in dangerous:
            raise SqlGuardError(f"function not allowed: {name}")
    for anon in statement.find_all(exp.Anonymous):
        if (anon.name or "").lower() in dangerous:
            raise SqlGuardError(f"function not allowed: {anon.name}")

    return statement.sql(dialect=dialect)
