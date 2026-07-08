"""Build an AI prompt that summarizes a result set and suggests a chart.

The default keeps the no-row-data promise: only column names/types and
*locally-computed* aggregates are sent to the model. A deployment may opt into
including a small sample of rows via ``AI_ALLOW_SAMPLE_ROWS``.
"""

from __future__ import annotations

import math
from typing import Any

from app.config import Settings
from app.schemas.execute import ResultColumn

_SUMMARY_SYSTEM_PROMPT = """\
You are a data analyst. You are given a description of a SQL query result set:
column names and types, locally-computed aggregate statistics, and optionally a
small sample of rows. Write a one or two sentence, plain-language summary of what
the results show, then suggest the best chart:
- "bar" for comparing one or more numeric values across categories (multiple
  numeric columns render as side-by-side bars),
- "hbar" (horizontal bar) for comparing across categories with long labels or a ranking,
- "line" for a trend over an ordered or time-based column (each numeric column is
  its own line),
- "area" for a cumulative trend over an ordered or time-based column,
- "pie" for parts of a whole across a small number of categories,
- "scatter" for the relationship between two numeric columns,
- "radar" for comparing 3-8 categories across one or more numeric measures,
- "combo" for mixing magnitudes (bars) with a rate or trend on a different scale
  (lines), e.g. revenue bars with a growth-percent line,
- "table" when a chart would not help,
- "none" if you are unsure.
Set x_column to the label/category/time column and y_columns to the numeric columns
to plot, in order (two numeric columns for "scatter": x_column and one y_columns
entry). When the data is "long" — a category column with a small distinct_count
whose values repeat for each x value — set series_column to that category column
and y_columns to the single numeric value column, so each category becomes its own
series. Set stacked=true only for "bar", "hbar", or "area" when the series are
parts of a whole per x value. For "combo", list in combo_line_columns the
y_columns to draw as lines; the rest are bars. Only use column names that appear
in the provided data; otherwise use null (and null for y_columns/combo_line_columns).
Write the summary in the same language as the original question when one is
provided (e.g. a Persian question gets a Persian summary); otherwise in English."""


def summary_system_prompt() -> str:
    return _SUMMARY_SYSTEM_PROMPT


def _to_number(value: Any) -> float | None:
    """Coerce a cell into a finite float, or None when not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            n = float(value)
        except ValueError:
            return None
        return n if math.isfinite(n) else None
    return None


def compute_column_stats(
    columns: list[ResultColumn], rows: list[list[Any]]
) -> list[dict[str, Any]]:
    """Per-column aggregates: null/distinct counts and numeric min/max/avg.

    A column is treated as numeric only when every non-null value parses as a
    number, so partially-numeric label columns are not mislabeled.
    """
    stats: list[dict[str, Any]] = []
    for ci, col in enumerate(columns):
        values = [row[ci] if ci < len(row) else None for row in rows]
        non_null = [v for v in values if v is not None]
        numbers = [n for n in (_to_number(v) for v in non_null) if n is not None]

        entry: dict[str, Any] = {
            "name": col.name,
            "type": col.type,
            "null_count": len(values) - len(non_null),
            "distinct_count": len({str(v) for v in non_null}),
        }
        if non_null and len(numbers) == len(non_null):
            entry["numeric"] = True
            entry["min"] = min(numbers)
            entry["max"] = max(numbers)
            entry["avg"] = round(sum(numbers) / len(numbers), 4)
        stats.append(entry)
    return stats


def _format_stat(entry: dict[str, Any]) -> str:
    parts = [f"{entry['name']} ({entry['type']})"]
    if entry.get("numeric"):
        parts.append(f"numeric: min={entry['min']}, max={entry['max']}, avg={entry['avg']}")
    parts.append(f"distinct={entry['distinct_count']}")
    parts.append(f"nulls={entry['null_count']}")
    return "- " + "; ".join(parts)


def build_summary_context(
    *,
    question: str | None,
    columns: list[ResultColumn],
    rows: list[list[Any]],
    settings: Settings,
) -> str:
    """Assemble the user-message context for the summary call.

    Includes raw rows ONLY when ``ai_allow_sample_rows`` is enabled, and then at
    most ``ai_sample_rows`` of them.
    """
    stats = compute_column_stats(columns, rows)
    lines: list[str] = []
    if question:
        lines.append(f"Original question: {question}")
    lines.append(f"Row count: {len(rows)}")
    lines.append("Columns and statistics:")
    lines.extend(_format_stat(s) for s in stats)

    if settings.ai_allow_sample_rows and settings.ai_sample_rows > 0 and rows:
        sample = rows[: settings.ai_sample_rows]
        header = ", ".join(c.name for c in columns)
        lines.append(f"\nSample rows (first {len(sample)}):")
        lines.append(header)
        for row in sample:
            lines.append(", ".join("" if v is None else str(v) for v in row))

    return "\n".join(lines)
