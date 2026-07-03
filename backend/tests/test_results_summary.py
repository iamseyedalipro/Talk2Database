"""Tests for result-summary aggregate computation and sample-row gating."""

from __future__ import annotations

from app.config import Settings
from app.schemas.execute import ResultColumn
from app.services.results_summary import build_summary_context, compute_column_stats

COLUMNS = [ResultColumn(name="day", type="date"), ResultColumn(name="orders", type="bigint")]
ROWS = [["2026-01-01", 10], ["2026-01-02", 20], ["2026-01-03", None]]


def _settings(**overrides: object) -> Settings:
    base = {
        "ai_api_key": "x",
        "ai_model": "m",
        "jwt_secret": "s",
        "connections_secret_key": "",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_numeric_column_stats() -> None:
    stats = {s["name"]: s for s in compute_column_stats(COLUMNS, ROWS)}

    orders = stats["orders"]
    assert orders["numeric"] is True
    assert orders["min"] == 10
    assert orders["max"] == 20
    assert orders["avg"] == 15  # average over non-null numeric values only
    assert orders["null_count"] == 1

    day = stats["day"]
    assert "numeric" not in day  # date labels are not numeric
    assert day["distinct_count"] == 3
    assert day["null_count"] == 0


def test_sample_rows_omitted_by_default() -> None:
    context = build_summary_context(
        question="orders per day", columns=COLUMNS, rows=ROWS, settings=_settings()
    )
    assert "Sample rows" not in context
    assert "Columns and statistics" in context
    assert "Row count: 3" in context


def test_sample_rows_included_and_capped_when_enabled() -> None:
    context = build_summary_context(
        question=None,
        columns=COLUMNS,
        rows=ROWS,
        settings=_settings(ai_allow_sample_rows=True, ai_sample_rows=2),
    )
    assert "Sample rows (first 2):" in context
    # Only the first two rows are present; the third is not sampled.
    assert "2026-01-01" in context
    assert "2026-01-02" in context
    assert "2026-01-03" not in context
