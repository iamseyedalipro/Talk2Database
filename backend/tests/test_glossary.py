"""Tests for rendering the business glossary into a prompt block."""

from __future__ import annotations

from app.models.glossary import GlossaryDescription, Metric
from app.services.schema.glossary import build_glossary_block


def _desc(table: str, column: str, text: str) -> GlossaryDescription:
    return GlossaryDescription(
        connection_id=1, table_name=table, column_name=column, description=text
    )


def _metric(name: str, definition: str, expression: str | None = None) -> Metric:
    return Metric(connection_id=1, name=name, definition=definition, expression=expression)


def test_empty_glossary_is_blank() -> None:
    assert build_glossary_block([], []) == ""


def test_descriptions_render_table_and_column_targets() -> None:
    block = build_glossary_block(
        [_desc("orders", "", "All customer orders"), _desc("orders", "total", "Amount in cents")],
        [],
    )
    assert "BUSINESS GLOSSARY" in block
    assert "- orders: All customer orders" in block
    assert "- orders.total: Amount in cents" in block
    assert "METRICS" not in block


def test_metrics_render_with_optional_expression() -> None:
    block = build_glossary_block(
        [],
        [
            _metric("MRR", "Sum of active monthly subscriptions", "SUM(amount)"),
            _metric("Active user", "Logged in within 30 days"),
        ],
    )
    assert "METRICS" in block
    assert "- MRR: Sum of active monthly subscriptions [SQL: SUM(amount)]" in block
    assert "- Active user: Logged in within 30 days" in block
    # No SQL suffix when no expression is provided.
    assert "Logged in within 30 days [SQL" not in block
