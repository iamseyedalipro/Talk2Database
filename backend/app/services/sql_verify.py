"""Verify that generated SQL only references tables/columns that really exist.

``sql_guard`` proves a statement is a single read-only SELECT; this module
proves it is *grounded*: every table and column it names must exist in the
connection's schema snapshot. Hallucinated identifiers are collected (never
raised) so the caller can feed them back to the model as a correction prompt.

Resolution uses sqlglot's scope analysis, which natively handles CTEs,
derived tables, aliases, subqueries and set operations. The checks are
deliberately biased toward false negatives — anything we cannot resolve with
confidence (correlated references, star-selecting CTEs, table functions) is
skipped, because the executing database remains the final arbiter.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from app.services.schema.introspect import SchemaData, TableInfo
from app.services.schema.serialize import serialize_table, table_directory

# Namespaces whose tables/columns are not in the snapshot but always exist.
_SYSTEM_SCHEMAS = frozenset(
    {"information_schema", "pg_catalog", "performance_schema", "mysql", "sys"}
)


@dataclass
class VerificationResult:
    """Identifiers in a statement that do not exist in the schema snapshot."""

    unknown_tables: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unknown_tables and not self.unknown_columns

    def describe(self) -> str:
        """One-line summary used in API responses and history rows."""
        parts: list[str] = []
        if self.unknown_tables:
            parts.append("unknown tables: " + ", ".join(self.unknown_tables))
        if self.unknown_columns:
            parts.append("unknown columns: " + ", ".join(self.unknown_columns))
        return "; ".join(parts)


class _Lookup:
    """Case-folded table/column lookups over a :class:`SchemaData`."""

    def __init__(self, schema: SchemaData) -> None:
        self.by_name: dict[str, list[TableInfo]] = {}
        self.by_qualified: dict[tuple[str, str], TableInfo] = {}
        for table in schema["tables"]:
            self.by_name.setdefault(table["name"].lower(), []).append(table)
            self.by_qualified[(table["schema"].lower(), table["name"].lower())] = table

    def resolve(self, db: str, name: str) -> list[TableInfo]:
        if db:
            hit = self.by_qualified.get((db.lower(), name.lower()))
            return [hit] if hit else []
        return self.by_name.get(name.lower(), [])


def _column_names(table: TableInfo) -> set[str]:
    return {column["name"].lower() for column in table["columns"]}


def _source_output_names(source: Scope) -> set[str] | None:
    """Visible column names of a CTE/derived-table source, or ``None`` if opaque."""
    names = source.expression.named_selects
    if "*" in names:
        return None
    return {name.lower() for name in names}


@dataclass
class _ScopeSources:
    """What a single scope's FROM/JOIN sources resolve to."""

    # alias/name -> candidate snapshot tables (only sources that resolved).
    tables: dict[str, list[TableInfo]] = field(default_factory=dict)
    # alias/name -> CTE / derived-table scope.
    ctes: dict[str, Scope] = field(default_factory=dict)
    # True when any source cannot be column-checked (system tables, table
    # functions, star-selecting CTEs, tables already flagged as unknown).
    opaque: bool = False


def verify_identifiers(sql: str, schema: SchemaData, dialect: str) -> VerificationResult:
    """Collect table/column references in ``sql`` that the snapshot does not contain."""
    result = VerificationResult()
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
        scopes = traverse_scope(tree)
    except Exception:
        # sql_guard already proved the statement parses; if scope analysis
        # still fails, let the database judge rather than block the query.
        return result

    lookup = _Lookup(schema)
    unknown_tables: list[str] = []
    unknown_columns: list[str] = []
    resolved: dict[int, _ScopeSources] = {}

    def scope_sources(scope: Scope) -> _ScopeSources:
        cached = resolved.get(id(scope))
        if cached is not None:
            return cached
        info = _ScopeSources()
        for name, source in scope.sources.items():
            if isinstance(source, Scope):
                info.ctes[name] = source
                if _source_output_names(source) is None:
                    info.opaque = True
                continue
            if not isinstance(source, exp.Table) or not isinstance(source.this, exp.Identifier):
                # Table functions (generate_series, unnest, ...), VALUES, etc.
                info.opaque = True
                continue
            db = source.text("db")
            if db.lower() in _SYSTEM_SCHEMAS:
                info.opaque = True
                continue
            candidates = lookup.resolve(db, source.name)
            if not candidates:
                display = f"{db}.{source.name}" if db else source.name
                unknown_tables.append(display)
                info.opaque = True
                continue
            info.tables[name] = candidates
        resolved[id(scope)] = info
        return info

    def check_qualified(scope: Scope, column: exp.Column) -> None:
        """Validate ``alias.column`` against whatever the alias resolves to."""
        qualifier, col_name = column.table, column.name.lower()
        current: Scope | None = scope
        while current is not None:
            source = current.sources.get(qualifier)
            if source is not None:
                break
            current = current.parent
        if current is None or source is None:
            return  # unresolvable qualifier — skip
        if isinstance(source, Scope):
            visible = _source_output_names(source)
            if visible is not None and col_name not in visible:
                unknown_columns.append(f"{qualifier}.{column.name}")
            return
        candidates = scope_sources(current).tables.get(qualifier)
        if candidates and not any(col_name in _column_names(t) for t in candidates):
            unknown_columns.append(f"{candidates[0]['name']}.{column.name}")

    def check_unqualified(scope: Scope, column: exp.Column) -> None:
        """Validate a bare column against every source visible from ``scope``."""
        col_name = column.name.lower()
        aliases = {
            s.alias.lower()
            for s in getattr(scope.expression, "selects", [])
            if isinstance(s, exp.Alias) and s.alias
        }
        if col_name in aliases:
            return  # references the scope's own select alias (ORDER BY total)
        current: Scope | None = scope
        while current is not None:
            info = scope_sources(current)
            if info.opaque:
                return  # cannot enumerate the columns in scope — skip
            for candidates in info.tables.values():
                if any(col_name in _column_names(t) for t in candidates):
                    return
            for cte in info.ctes.values():
                visible = _source_output_names(cte)
                if visible is not None and col_name in visible:
                    return
            current = current.parent
        unknown_columns.append(column.name)

    for scope in scopes:
        scope_sources(scope)  # flag unknown tables even when no columns reference them
        for column in scope.columns:
            if column.table:
                check_qualified(scope, column)
            else:
                check_unqualified(scope, column)

    result.unknown_tables = list(dict.fromkeys(unknown_tables))
    result.unknown_columns = list(dict.fromkeys(unknown_columns))
    return result


def build_correction_feedback(result: VerificationResult, schema: SchemaData) -> str:
    """The corrective user message sent back to the model after a failed check."""
    all_table_names = [t["name"] for t in schema["tables"]]
    tables_by_name = {t["name"].lower(): t for t in schema["tables"]}

    lines: list[str] = [
        "Your previous query referenced identifiers that DO NOT exist in the schema.",
        "",
    ]
    for name in result.unknown_tables:
        bare = name.rsplit(".", 1)[-1]
        close = difflib.get_close_matches(bare, all_table_names, n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        lines.append(f'- Table "{name}" does not exist.{hint}')

    shown_tables: set[str] = set()
    for ref in result.unknown_columns:
        table_part, _, column_part = ref.rpartition(".")
        table = tables_by_name.get(table_part.lower()) if table_part else None
        if table is not None:
            real = [c["name"] for c in table["columns"]]
            close = difflib.get_close_matches(column_part, real, n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            lines.append(f'- Column "{ref}" does not exist.{hint}')
            if table["name"] not in shown_tables:
                shown_tables.add(table["name"])
                lines.extend(["", serialize_table(table), ""])
        else:
            lines.append(f'- Column "{ref}" does not exist in any table in scope.')

    lines.extend(
        [
            "",
            table_directory(schema),
            "",
            "Rewrite the query using ONLY tables and columns from the schema. "
            "If the question truly cannot be mapped to this schema, return "
            'status "needs_clarification" with concrete suggested interpretations '
            "instead of inventing identifiers.",
        ]
    )
    return "\n".join(lines)
