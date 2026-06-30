"""Parse database EXPLAIN (FORMAT JSON) output into a cost/row estimate.

Kept dialect-specific and pure so it can be unit-tested without a live database.
Both parsers are best-effort: any unexpected shape yields ``None`` rather than
raising, since EXPLAIN output varies across server versions.
"""

from __future__ import annotations

import json
from typing import Any


def _as_object(payload: Any) -> Any:
    """Return a parsed object whether ``payload`` is JSON text or already parsed."""
    if isinstance(payload, (dict, list)):
        return payload
    if isinstance(payload, (str, bytes, bytearray)):
        return json.loads(payload)
    raise TypeError("unsupported EXPLAIN payload")


def parse_postgres_explain(payload: Any) -> tuple[float | None, int | None]:
    """Extract (total cost, estimated rows) from ``EXPLAIN (FORMAT JSON)`` output.

    Postgres returns ``[{"Plan": {"Total Cost": ..., "Plan Rows": ...}}]``.
    """
    try:
        data = _as_object(payload)
        plan = data[0]["Plan"]
        cost = plan.get("Total Cost")
        rows = plan.get("Plan Rows")
        return (
            float(cost) if cost is not None else None,
            int(rows) if rows is not None else None,
        )
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None, None


def parse_mysql_explain(payload: Any) -> tuple[float | None, int | None]:
    """Extract (query cost, estimated rows) from ``EXPLAIN FORMAT=JSON`` output.

    MySQL returns ``{"query_block": {"cost_info": {"query_cost": "..."}, ...}}``.
    Estimated rows are read best-effort from the outermost table node.
    """
    try:
        data = _as_object(payload)
        block = data["query_block"]
        cost_raw = block.get("cost_info", {}).get("query_cost")
        cost = float(cost_raw) if cost_raw is not None else None
        return cost, _mysql_estimated_rows(block)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, None


def _mysql_estimated_rows(block: dict[str, Any]) -> int | None:
    """Best-effort estimated row count from a MySQL ``query_block``."""
    table = block.get("table")
    if isinstance(table, dict):
        for key in ("rows_produced_per_join", "rows_examined_per_scan"):
            value = table.get(key)
            if value is not None:
                return int(value)
    # Nested shapes (ordering/grouping/joins) wrap another query_block.
    for key in ("ordering_operation", "grouping_operation"):
        nested = block.get(key)
        if isinstance(nested, dict):
            return _mysql_estimated_rows(nested)
    return None
