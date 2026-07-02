"""Render glossary descriptions and metrics into a prompt block for the AI.

The block is appended to the serialized schema so the model can resolve business
terms ("active user", "MRR") and table/column meaning when generating SQL.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryDescription, Metric


async def load_glossary(
    session: AsyncSession, connection_id: int
) -> tuple[list[GlossaryDescription], list[Metric]]:
    """Fetch a connection's descriptions and metrics."""
    descriptions = (
        (
            await session.execute(
                select(GlossaryDescription).where(
                    GlossaryDescription.connection_id == connection_id
                )
            )
        )
        .scalars()
        .all()
    )
    metrics = (
        (await session.execute(select(Metric).where(Metric.connection_id == connection_id)))
        .scalars()
        .all()
    )
    return list(descriptions), list(metrics)


def _target(entry: GlossaryDescription) -> str:
    return entry.table_name if not entry.column_name else f"{entry.table_name}.{entry.column_name}"


def build_glossary_block(
    descriptions: Sequence[GlossaryDescription], metrics: Sequence[Metric]
) -> str:
    """Return a text block for the prompt, or ``""`` when there is nothing to add."""
    sections: list[str] = []

    if descriptions:
        lines = ["BUSINESS GLOSSARY (human-written meanings; trust these for intent):"]
        for entry in sorted(descriptions, key=lambda d: (d.table_name, d.column_name)):
            lines.append(f"- {_target(entry)}: {entry.description}")
        sections.append("\n".join(lines))

    if metrics:
        lines = ["METRICS (use these definitions when the question mentions them):"]
        for metric in sorted(metrics, key=lambda m: m.name):
            text = f"- {metric.name}: {metric.definition}"
            if metric.expression:
                text += f" [SQL: {metric.expression}]"
            lines.append(text)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
