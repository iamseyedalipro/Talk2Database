"""Semantic layer: human-written descriptions and business metrics.

These annotations are attached to a connection's schema and fed into the AI
prompt, which dramatically improves SQL accuracy on real-world schemas. A
``column_name`` of ``""`` denotes a table-level description.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class GlossaryDescription(Base, TimestampMixin):
    __tablename__ = "glossary_descriptions"
    __table_args__ = (
        UniqueConstraint("connection_id", "table_name", "column_name", name="uq_glossary_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Empty string => the description applies to the table itself.
    column_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Metric(Base, TimestampMixin):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("connection_id", "name", name="uq_metric_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional canonical SQL expression for the metric.
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
